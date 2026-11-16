"""Medidas por HTTP: `POST` y `GET /athletes/{member_id}/metrics` (S9-A1, US-178). Rojo A1.

Contrato del blueprint §3, rutas 1 y 2.

- Admin y coach crean (201) y listan (200); `member` 403 `forbidden`; sin token 401; en modo quiosco
  403 `kiosk_mode` (la ruta no está entre las 12 permitidas) sin dejar filas.
- 422 `validation_error` con `field` y sin repetir el valor; cuerpo con claves de más 422.
- 404 `member_not_found` (inexistente o dado de baja, solo al escribir); 409 `consent_required`.
- `Cache-Control: no-store`; la cubeta `athletes-write` (30 por minuto) cuenta solo las escrituras:
  un 403 no consume cupo y la lectura usa `staff-read`.
- El valor de una medida nunca vuelve en la respuesta (solo `has_*`).
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
from tests.athletes._apoyo import ATHLETES, cuerpo, ruta_metricas
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.athletes import make_metric
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "id",
    "measured_on",
    "has_weight",
    "has_height",
    "has_body_fat",
    "has_notes",
    "recorded_by",
    "recorded_by_name",
    "voided_at",
    "created_at",
}
TOPE_ESCRITURAS = 30


def test_el_router_publica_las_rutas_de_medidas() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert {
        ("POST", "/athletes/{member_id}/metrics"),
        ("GET", "/athletes/{member_id}/metrics"),
    } <= publicadas
    assert not any(m in {"DELETE", "PUT", "PATCH"} for m, ruta in publicadas if "metrics" in ruta)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_crean_y_listan(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien = await usuario_real(rol)
    miembro = await socio(session, consentido=True)

    r = await app_http.post(ruta_metricas(miembro.id), json=cuerpo(), headers=cabeceras(quien))

    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS
    assert (datos["has_weight"], datos["has_height"], datos["has_body_fat"]) == (True, True, True)
    assert datos["has_notes"] is True and datos["recorded_by"] == str(quien.id)
    assert datos["measured_on"] == "2026-10-20" and datos["voided_at"] is None
    texto = r.text
    for claro in ("62500", "62.5", "Primera medición"):
        assert claro not in texto

    lista = await app_http.get(ruta_metricas(miembro.id), headers=cabeceras(quien))
    assert lista.status_code == 200
    assert lista.headers["cache-control"] == "no-store"
    pagina = lista.json()
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (1, 25, 0)
    assert pagina["items"][0]["id"] == datos["id"] and set(pagina["items"][0]) == CAMPOS


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    miembro = await socio(session, consentido=True)
    ruta = ruta_metricas(miembro.id)
    rol_socio = await usuario_real("member")
    for metodo, cuerpo_json in (("GET", None), ("POST", cuerpo())):
        r = await app_http.request(metodo, ruta, json=cuerpo_json, headers=cabeceras(rol_socio))
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "forbidden"
        sin = await app_http.request(metodo, ruta, json=cuerpo_json)
        assert sin.status_code == 401
        assert sin.json()["error"]["code"] == "unauthorized"
    assert await session.scalar(text("SELECT count(*) FROM athletes.body_metrics")) == 0


async def test_en_modo_quiosco_403_kiosk_mode_sin_dejar_filas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    miembro = await socio(session, consentido=True)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    for metodo, cuerpo_json in (("POST", cuerpo()), ("GET", None)):
        r = await app_http.request(metodo, ruta_metricas(miembro.id), json=cuerpo_json, headers=cab)
        assert r.status_code == 403, (metodo, r.text)
        assert r.json()["error"]["code"] == "kiosk_mode"
    assert await session.scalar(text("SELECT count(*) FROM athletes.body_metrics")) == 0


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"weight_g": 19_999}, "weight_g"),
        ({"weight_g": 400_001}, "weight_g"),
        ({"weight_g": "pesado"}, "weight_g"),
        ({"height_cm": 49}, "height_cm"),
        ({"height_cm": 251}, "height_cm"),
        ({"body_fat_pct": 0}, "body_fat_pct"),
        ({"body_fat_pct": 76}, "body_fat_pct"),
        ({"notes": ""}, "notes"),
        ({"notes": "a" * 501}, "notes"),
        ({"measured_on": "2026-10-22"}, "measured_on"),  # mañana en Bogotá
        ({"measured_on": "1999-12-31"}, "measured_on"),
        ({"measured_on": "no es fecha"}, "measured_on"),
    ],
)
async def test_422_por_campo_sin_repetir_el_valor(
    cambios: dict[str, Any],
    campo: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("coach"))
    miembro = await socio(session, consentido=True)

    r = await app_http.post(ruta_metricas(miembro.id), json=cuerpo(**cambios), headers=h)

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    for valor in cambios.values():
        if str(valor) not in {"", "0", "49", "76", "251"}:
            assert str(valor) not in r.text, valor
    assert await session.scalar(text("SELECT count(*) FROM athletes.body_metrics")) == 0


async def test_los_errores_422_404_y_409_llevan_no_store(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """L-B de la revisión de A1: `no-store` en TODO error (incluido el 422 de Pydantic)."""
    h = cabeceras(await usuario_real("coach"))
    miembro = await socio(session, consentido=True)
    ruta = ruta_metricas(miembro.id)

    pydantic = await app_http.post(ruta, json=cuerpo(weight_g="pesado"), headers=h)
    assert pydantic.status_code == 422
    assert pydantic.headers["cache-control"] == "no-store"
    lista = await app_http.get(ruta, params={"limit": 0}, headers=h)
    assert lista.status_code == 422 and lista.headers["cache-control"] == "no-store"


async def test_422_sin_ninguna_de_las_tres_medidas_y_con_claves_de_mas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("coach"))
    miembro = await socio(session, consentido=True)
    ruta = ruta_metricas(miembro.id)

    sin_medidas = await app_http.post(
        ruta, json={"measured_on": "2026-10-20", "notes": "solo texto"}, headers=h
    )
    assert sin_medidas.status_code == 422
    assert sin_medidas.json()["error"]["field"] == "weight_g"
    sin_fecha = await app_http.post(ruta, json={"weight_g": 62_500}, headers=h)
    assert sin_fecha.status_code == 422 and sin_fecha.json()["error"]["field"] == "measured_on"
    de_mas = await app_http.post(ruta, json=cuerpo(member_id=str(uuid4())), headers=h)
    assert de_mas.status_code == 422
    voided = await app_http.post(ruta, json=cuerpo(voided_at="2026-10-20T00:00:00Z"), headers=h)
    assert voided.status_code == 422


async def test_404_con_socio_inexistente_o_dado_de_baja_y_la_lista_del_baja_se_lee(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("admin"))
    inexistente = await app_http.post(ruta_metricas(uuid4()), json=cuerpo(), headers=h)
    assert inexistente.status_code == 404
    assert inexistente.json()["error"]["code"] == "member_not_found"
    assert inexistente.headers["cache-control"] == "no-store"
    assert (await app_http.get(ruta_metricas(uuid4()), headers=h)).status_code == 404

    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    await make_metric(session, baja.id)
    ruta_baja = ruta_metricas(baja.id)  # antes del 404: revierte la sesión y expira `baja`
    escribir = await app_http.post(ruta_baja, json=cuerpo(), headers=h)
    assert escribir.status_code == 404 and escribir.json()["error"]["code"] == "member_not_found"
    leer = await app_http.get(ruta_baja, headers=h)
    assert leer.status_code == 200 and leer.json()["total"] == 1


async def test_409_consent_required_sin_dejar_filas_ni_operaciones_encrypt(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("coach"))
    miembro = await socio(session, consentido=False)
    antes = await session.scalar(
        text("SELECT coalesce(sum(count), 0) FROM crypto.crypto_ops WHERE data_class = :c"),
        {"c": "athlete.metric"},
    )

    r = await app_http.post(ruta_metricas(miembro.id), json=cuerpo(), headers=h)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "consent_required"
    assert r.headers["cache-control"] == "no-store"
    assert await session.scalar(text("SELECT count(*) FROM athletes.body_metrics")) == 0
    despues = await session.scalar(
        text("SELECT coalesce(sum(count), 0) FROM crypto.crypto_ops WHERE data_class = :c"),
        {"c": "athlete.metric"},
    )
    assert despues == antes


async def test_la_lista_pagina_filtra_anuladas_y_valida_los_parametros(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("coach"))
    miembro = await socio(session, consentido=True)
    viva = await make_metric(session, miembro.id)
    anulada = await make_metric(session, miembro.id, voided=True)
    ruta = ruta_metricas(miembro.id)

    por_defecto = (await app_http.get(ruta, headers=h)).json()
    assert [m["id"] for m in por_defecto["items"]] == [str(viva.id)]
    todas = (await app_http.get(ruta, params={"include_voided": "true"}, headers=h)).json()
    assert {m["id"] for m in todas["items"]} == {str(viva.id), str(anulada.id)}
    assert todas["total"] == 2
    pagina = (await app_http.get(ruta, params={"limit": 1, "offset": 1}, headers=h)).json()
    assert (pagina["limit"], pagina["offset"], pagina["total"]) == (1, 1, 1)
    for params in ({"limit": 201}, {"limit": 0}, {"offset": -1}):
        r = await app_http.get(ruta, params=params, headers=h)
        assert r.status_code == 422, params


async def test_cubeta_athletes_write_30_por_minuto_y_la_lectura_no_la_consume(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    h = cabeceras(await usuario_real("admin"))
    miembro = await socio(session, consentido=True)
    ruta = ruta_metricas(miembro.id)
    for i in range(TOPE_ESCRITURAS):
        r = await app_http.post(ruta, json=cuerpo(weight_g=60_000 + i), headers=h)
        assert r.status_code == 201, (i, r.text)
        assert (await app_http.get(ruta, headers=h)).status_code == 200  # `staff-read`, otra cubeta

    r = await app_http.post(ruta, json=cuerpo(), headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers
    assert (await app_http.get(ruta, headers=h)).status_code == 200
    assert ATHLETES in ruta


async def test_un_403_no_consume_cupo_de_escritura(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    miembro = await socio(session, consentido=True)
    rol_socio = await usuario_real("member")
    ruta = ruta_metricas(miembro.id)  # antes del bucle: un 403 revierte y expira `miembro`
    for _ in range(TOPE_ESCRITURAS + 2):
        r = await app_http.post(ruta, json=cuerpo(), headers=cabeceras(rol_socio))
        assert r.status_code == 403
