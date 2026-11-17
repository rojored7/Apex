"""Récords por HTTP: `POST` y `GET /athletes/{member_id}/records` (S9-B1, US-180). Rojo B1.

Contrato del blueprint §3, rutas 4 y 5.

- Admin y coach crean (201) y listan (200); `member` 403 `forbidden`; sin token 401; en modo quiosco
  403 `kiosk_mode` (la ruta no está entre las 12 permitidas) sin dejar filas.
- `extra="forbid"`: `capped`, `source`, `result_id`, `member_id` o `invalidated_*` dan 422 y no
  dejan filas; 422 con `field` y sin repetir el valor; `no-store` en todo error.
- 404 `member_not_found` al escribir (inexistente o dado de baja); la lista del baja se lee.
- `GET`: `kind` inválido 422 `field = "kind"`; filtro por `kind`; `include_invalidated`; paginación.
- La cubeta `athletes-write` (30 por minuto) cuenta solo las escrituras; la lectura usa
  `staff-read`; un 403 no consume cupo.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from app.modules.athletes.router import router
from tests.athletes._apoyo import cuerpo_benchmark, cuerpo_rm, ruta_records
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.athletes import make_record
from tests.factories.wods import make_benchmark, make_movement
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "id",
    "kind",
    "movement_id",
    "movement_name",
    "benchmark_id",
    "benchmark_name",
    "score_type",
    "value_g",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
    "achieved_on",
    "source",
    "result_id",
    "wod_id",
    "is_current",
    "invalidated_at",
    "invalidated_reason",
    "recorded_by",
    "recorded_by_name",
    "created_at",
}
TOPE_ESCRITURAS = 30


async def _cuenta(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM athletes.personal_records")) or 0)


def test_el_router_publica_las_rutas_de_records_y_ninguna_de_edicion() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert {
        ("POST", "/athletes/{member_id}/records"),
        ("GET", "/athletes/{member_id}/records"),
    } <= publicadas
    assert not any(m in {"DELETE", "PUT", "PATCH"} for m, ruta in publicadas if "records" in ruta)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_y_listan(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien = await usuario_real(rol)
    miembro = await socio(session, consentido=False)
    mov = await make_movement(session, quien.id, "Back Squat", "kg")
    ruta = ruta_records(miembro.id)
    cuerpo = cuerpo_rm(mov.id)

    r = await app_http.post(ruta, json=cuerpo, headers=cabeceras(quien))

    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS
    assert (datos["kind"], datos["source"], datos["is_current"]) == ("rm", "manual", True)
    assert (datos["value_g"], datos["achieved_on"]) == (100_000, "2026-10-20")
    assert datos["movement_name"] == "Back Squat" and datos["recorded_by"] == str(quien.id)
    assert (datos["result_id"], datos["wod_id"], datos["invalidated_at"]) == (None, None, None)

    lista = await app_http.get(ruta, headers=cabeceras(quien))
    assert lista.status_code == 200
    assert lista.headers["cache-control"] == "no-store"
    pagina = lista.json()
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (1, 25, 0)
    assert pagina["items"][0]["id"] == datos["id"] and set(pagina["items"][0]) == CAMPOS


async def test_un_benchmark_por_http_trae_nombre_y_tipo_de_marca(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Fran", "time")

    r = await app_http.post(
        ruta_records(miembro.id), json=cuerpo_benchmark(bm.id), headers=cabeceras(coach)
    )

    assert r.status_code == 201, r.text
    datos = r.json()
    assert (datos["kind"], datos["benchmark_name"], datos["score_type"]) == (
        "benchmark",
        "Fran",
        "time",
    )
    assert (datos["level"], datos["seconds"], datos["capped"]) == ("rx", 300, False)


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    miembro = await socio(session)
    ruta = ruta_records(miembro.id)
    rol_socio = await usuario_real("member")
    for metodo, cuerpo_json in (("GET", None), ("POST", cuerpo_rm(uuid4()))):
        r = await app_http.request(metodo, ruta, json=cuerpo_json, headers=cabeceras(rol_socio))
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
        sin = await app_http.request(metodo, ruta, json=cuerpo_json)
        assert sin.status_code == 401
        assert sin.json()["error"]["code"] == "unauthorized"
    assert await _cuenta(session) == 0


async def test_en_modo_quiosco_403_kiosk_mode_sin_dejar_filas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    for metodo, cuerpo_json in (("POST", cuerpo_rm(uuid4())), ("GET", None)):
        r = await app_http.request(metodo, ruta_records(miembro.id), json=cuerpo_json, headers=cab)
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "kiosk_mode"
    assert await _cuenta(session) == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"capped": True},
        {"source": "derived"},
        {"result_id": str(uuid4())},
        {"wod_id": str(uuid4())},
        {"member_id": str(uuid4())},
        {"invalidated_at": "2026-10-20T00:00:00Z"},
        {"invalidated_reason": "manual_error"},
        {"is_current": True},
    ],
)
async def test_claves_de_mas_dan_422_y_no_dejan_filas(
    extra: dict[str, Any],
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Extra", "kg")

    r = await app_http.post(
        ruta_records(miembro.id), json={**cuerpo_rm(mov.id), **extra}, headers=cabeceras(coach)
    )

    assert r.status_code == 422, r.text
    assert r.headers["cache-control"] == "no-store"
    assert await _cuenta(session) == 0


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"kind": "pr"}, "kind"),
        ({"kind": None}, "kind"),
        ({"achieved_on": None}, "achieved_on"),
        ({"achieved_on": "no es fecha"}, "achieved_on"),
        ({"achieved_on": "2026-10-22"}, "achieved_on"),  # mañana en Bogotá
        ({"achieved_on": "1999-12-31"}, "achieved_on"),
        ({"value_g": "pesado"}, "value_g"),
        ({"value_g": 100_000.5}, "value_g"),
        ({"value_g": 0}, "value_g"),
        ({"value_g": 1_000_001}, "value_g"),
        ({"movement_id": "no-es-uuid"}, "movement_id"),
        ({"movement_id": str(uuid4())}, "movement_id"),
    ],
)
async def test_422_por_campo(
    cambios: dict[str, Any],
    campo: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Campos", "kg")
    cuerpo = {**cuerpo_rm(mov.id), **cambios}
    cuerpo = {k: v for k, v in cuerpo.items() if v is not None}

    r = await app_http.post(ruta_records(miembro.id), json=cuerpo, headers=cabeceras(coach))

    assert r.status_code == 422, r.text
    assert r.headers["cache-control"] == "no-store"
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    for valor in cambios.values():
        if isinstance(valor, str) and len(valor) > 4:
            assert valor not in r.text, valor
    assert await _cuenta(session) == 0


async def test_404_con_socio_inexistente_o_dado_de_baja_y_la_lista_del_baja_se_lee(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    mov = await make_movement(session, admin.id, "Baja", "kg")
    cuerpo = cuerpo_rm(mov.id)
    inexistente = await app_http.post(ruta_records(uuid4()), json=cuerpo, headers=h)
    assert inexistente.status_code == 404
    assert inexistente.json()["error"]["code"] == "member_not_found"
    assert inexistente.headers["cache-control"] == "no-store"
    assert (await app_http.get(ruta_records(uuid4()), headers=h)).status_code == 404

    baja = await socio(session, deleted_at=ANTES, status="inactive")
    await make_record(session, baja.id)
    ruta_baja = ruta_records(baja.id)  # antes del 404: revierte la sesión y expira `baja`
    escribir = await app_http.post(ruta_baja, json=cuerpo, headers=h)
    assert escribir.status_code == 404 and escribir.json()["error"]["code"] == "member_not_found"
    leer = await app_http.get(ruta_baja, headers=h)
    assert leer.status_code == 200 and leer.json()["total"] == 1


async def test_get_kind_invalido_422_field_kind_y_el_filtro_funciona(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Filtro", "kg")
    bm = await make_benchmark(session, coach.id, "Filtro Bm", "time")
    rm = await make_record(session, miembro.id, movement_id=mov.id, actor=coach.id)
    marca = await make_record(
        session, miembro.id, kind="benchmark", benchmark_id=bm.id, actor=coach.id
    )
    ruta = ruta_records(miembro.id)

    malo = await app_http.get(ruta, params={"kind": "pr"}, headers=h)
    assert malo.status_code == 422 and malo.json()["error"]["field"] == "kind"
    assert malo.headers["cache-control"] == "no-store"
    solo_rm = (await app_http.get(ruta, params={"kind": "rm"}, headers=h)).json()
    solo_bm = (await app_http.get(ruta, params={"kind": "benchmark"}, headers=h)).json()
    assert [i["id"] for i in solo_rm["items"]] == [str(rm.id)]
    assert [i["id"] for i in solo_bm["items"]] == [str(marca.id)]


async def test_la_lista_pagina_filtra_invalidados_y_valida_los_parametros(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Paginas", "kg")
    viva = await make_record(session, miembro.id, movement_id=mov.id, actor=coach.id)
    invalidada = await make_record(
        session, miembro.id, movement_id=mov.id, value_g=150_000, invalidated=True, actor=coach.id
    )
    ruta = ruta_records(miembro.id)

    por_defecto = (await app_http.get(ruta, headers=h)).json()
    assert [r["id"] for r in por_defecto["items"]] == [str(viva.id)]
    assert por_defecto["items"][0]["is_current"] is True
    todas = (await app_http.get(ruta, params={"include_invalidated": "true"}, headers=h)).json()
    assert {r["id"] for r in todas["items"]} == {str(viva.id), str(invalidada.id)}
    assert todas["total"] == 2
    marcada = next(r for r in todas["items"] if r["id"] == str(invalidada.id))
    assert (marcada["is_current"], marcada["invalidated_reason"]) == (False, "manual_error")
    pagina = (
        await app_http.get(
            ruta, params={"limit": 1, "offset": 1, "include_invalidated": "true"}, headers=h
        )
    ).json()
    assert (pagina["limit"], pagina["offset"], pagina["total"], len(pagina["items"])) == (
        1,
        1,
        2,
        1,
    )
    for params in ({"limit": 201}, {"limit": 0}, {"offset": -1}):
        r = await app_http.get(ruta, params=params, headers=h)
        assert r.status_code == 422, params


async def test_cubeta_athletes_write_30_por_minuto_y_la_lectura_no_la_consume(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    miembro = await socio(session)
    mov = await make_movement(session, admin.id, "Cubeta", "kg")
    ruta = ruta_records(miembro.id)
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(ruta, json=cuerpo_rm(mov.id, value_g=1_000 + i), headers=h)
        assert r.status_code == 201, (i, r.text)
        assert (await app_http.get(ruta, headers=h)).status_code == 200  # `staff-read`, otra cubeta

    r = await app_http.post(ruta, json=cuerpo_rm(mov.id), headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers
    assert (await app_http.get(ruta, headers=h)).status_code == 200


async def test_un_403_no_consume_cupo_de_escritura(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    miembro = await socio(session)
    rol_socio = await usuario_real("member")
    ruta = ruta_records(miembro.id)  # antes del bucle: un 403 revierte y expira `miembro`
    for _ in range(TOPE_ESCRITURAS + 2):
        r = await app_http.post(ruta, json=cuerpo_rm(uuid4()), headers=cabeceras(rol_socio))
        assert r.status_code == 403
