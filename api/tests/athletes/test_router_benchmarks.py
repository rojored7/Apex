"""Benchmarks por HTTP: `GET /athletes/{member_id}/benchmarks` y `.../{benchmark_id}` (S9-C1).

Contrato del blueprint §3, rutas 8 y 9.
- Admin y coach leen (200, `Cache-Control: no-store`); `member` 403 `forbidden`; sin token 401; en
  modo quiosco 403 `kiosk_mode` (la ruta no está entre las 12 permitidas).
- La lista pagina (`limit` 1..200, `offset` >= 0; 422 fuera de rango); la serie no pagina.
- 404 `member_not_found` y 404 `benchmark_not_found`; un id que no es UUID da 422.
- Solo lectura: ningún método de escritura en estas rutas. Usan la cubeta `staff-read` (120 por
  minuto) y no consumen `athletes-write`.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from app.modules.athletes.router import router
from tests.athletes._apoyo import ATHLETES
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.wods import make_benchmark, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

FILA = {"benchmark_id", "name", "score_type", "attempts", "best", "last_on"}
MARCA = {"level", "seconds", "rounds", "reps", "load_g", "capped"}
INTENTO = MARCA | {"result_id", "wod_id", "wod_date", "source", "is_best", "level_changed"}
SERIE = {"benchmark_id", "name", "score_type", "attempts", "truncated"}
TOPE_LECTURAS = 120


def _lista(member_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/benchmarks"


def _serie(member_id: UUID | str, benchmark_id: UUID | str) -> str:
    return f"{_lista(member_id)}/{benchmark_id}"


async def _con_intentos(session: AsyncSession) -> tuple[Escena, UUID]:
    e = await escena(session, score_type="time", fecha="2026-08-20", con_clase=False)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    for dia, seg in (("2026-09-01", 300), ("2026-09-08", 270)):
        wod = (
            await make_wod(
                session,
                e.coach,
                list(e.movimientos),
                date=dia,
                title=f"Fran {dia}",
                score_type="time",
                time_cap_s=900,
                benchmark_id=str(fran),
            )
        ).id
        await registrar(session, dataclasses.replace(e, wod_id=wod), seconds=seg)
    return e, fran


def test_el_router_publica_solo_lecturas_de_benchmarks() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
        if "benchmarks" in ruta.path
    }
    assert publicadas == {
        ("GET", "/athletes/{member_id}/benchmarks"),
        ("GET", "/athletes/{member_id}/benchmarks/{benchmark_id}"),
    }


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_leen_la_lista_y_la_serie(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien = await usuario_real(rol)
    e, fran = await _con_intentos(session)
    h = cabeceras(quien)
    ruta_lista, ruta_serie = _lista(e.socio_id), _serie(e.socio_id, fran)

    lista = await app_http.get(ruta_lista, headers=h)
    serie = await app_http.get(ruta_serie, headers=h)

    assert lista.status_code == 200, lista.text
    assert lista.headers["cache-control"] == "no-store"
    pagina = lista.json()
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (1, 25, 0)
    (fila,) = pagina["items"]
    assert set(fila) == FILA and set(fila["best"]) == MARCA
    assert (fila["name"], fila["attempts"], fila["best"]["seconds"]) == ("Fran", 2, 270)
    assert serie.status_code == 200, serie.text
    assert serie.headers["cache-control"] == "no-store"
    cuerpo: dict[str, Any] = serie.json()
    assert set(cuerpo) == SERIE
    assert [set(a) for a in cuerpo["attempts"]] == [INTENTO, INTENTO]
    assert [(a["seconds"], a["is_best"], a["level_changed"]) for a in cuerpo["attempts"]] == [
        (300, False, False),
        (270, True, False),
    ]


async def test_la_serie_de_un_benchmark_sin_intentos_es_200_con_lista_vacia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, _ = await _con_intentos(session)
    otro = await make_benchmark(session, coach.id, "Helen", "time")

    r = await app_http.get(_serie(e.socio_id, otro.id), headers=cabeceras(coach))

    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["attempts"]) == ("Helen", [])


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e, fran = await _con_intentos(session)
    rol_socio = await usuario_real("member")
    for ruta in (_lista(e.socio_id), _serie(e.socio_id, fran)):
        r = await app_http.get(ruta, headers=cabeceras(rol_socio))
        assert r.status_code == 403, (ruta, r.text)
        assert r.json()["error"]["code"] == "forbidden"
        sin = await app_http.get(ruta)
        assert sin.status_code == 401
        assert sin.json()["error"]["code"] == "unauthorized"


async def test_en_modo_quiosco_403_kiosk_mode(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, fran = await _con_intentos(session)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    for ruta in (_lista(e.socio_id), _serie(e.socio_id, fran)):
        r = await app_http.get(ruta, headers=cab)
        assert r.status_code == 403, (ruta, r.text)
        assert r.json()["error"]["code"] == "kiosk_mode"


async def test_404_de_socio_y_de_benchmark_inexistentes(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, fran = await _con_intentos(session)
    h = cabeceras(coach)

    sin_socio = await app_http.get(_lista(uuid4()), headers=h)
    serie_sin_socio = await app_http.get(_serie(uuid4(), fran), headers=h)
    sin_benchmark = await app_http.get(_serie(e.socio_id, uuid4()), headers=h)

    for r in (sin_socio, serie_sin_socio):
        assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"
    assert sin_benchmark.status_code == 404
    assert sin_benchmark.json()["error"]["code"] == "benchmark_not_found"
    assert sin_benchmark.headers["cache-control"] == "no-store"


async def test_ids_mal_formados_dan_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, _ = await _con_intentos(session)
    h = cabeceras(coach)

    assert (await app_http.get(_serie(e.socio_id, "no-es-uuid"), headers=h)).status_code == 422
    assert (await app_http.get(_lista("no-es-uuid"), headers=h)).status_code == 422


async def test_la_lista_valida_y_aplica_la_paginacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, _ = await _con_intentos(session)
    h = cabeceras(coach)
    ruta = _lista(e.socio_id)

    for params in ({"limit": 201}, {"limit": 0}, {"offset": -1}):
        r = await app_http.get(ruta, params=params, headers=h)
        assert r.status_code == 422, params
    fuera = await app_http.get(ruta, params={"limit": 1, "offset": 5}, headers=h)
    assert fuera.status_code == 200
    assert (fuera.json()["total"], fuera.json()["items"]) == (1, [])


async def test_cubeta_staff_read_120_por_minuto_y_no_toca_athletes_write(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, fran = await _con_intentos(session)
    h = cabeceras(coach)
    ruta = _lista(e.socio_id)
    for i in range(TOPE_LECTURAS):
        r = await app_http.get(ruta if i % 2 else _serie(e.socio_id, fran), headers=h)
        assert r.status_code == 200, (i, r.text)

    r = await app_http.get(ruta, headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers


async def test_la_lista_acepta_q_y_la_serie_publica_truncated(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    e, fran = await _con_intentos(session)
    h = cabeceras(coach)

    con = await app_http.get(_lista(e.socio_id), params={"q": "FRAN"}, headers=h)
    sin = await app_http.get(_lista(e.socio_id), params={"q": "zzz"}, headers=h)
    larga = await app_http.get(_lista(e.socio_id), params={"q": "x" * 101}, headers=h)
    serie = await app_http.get(_serie(e.socio_id, fran), headers=h)

    assert con.status_code == 200 and con.json()["total"] == 1
    assert sin.status_code == 200 and sin.json()["total"] == 0
    assert larga.status_code == 422 and larga.json()["error"]["field"] == "q"
    assert serie.json()["truncated"] is False
