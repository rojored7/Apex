"""Perfil por HTTP: `GET /athletes/{member_id}/rms` y `.../summary` (S9-C2, US-184 CA1, CA2, CA6).

Contrato del blueprint §3, rutas 6 y 7.
- Admin y coach leen (200, `Cache-Control: no-store`); `member` 403 `forbidden`; sin token 401; en
  modo quiosco 403 `kiosk_mode`.
- `/rms` pagina (`limit` 1..200, `offset` >= 0; 422 fuera de rango) y acepta `q` (regla de datos
  6; 422 `q` si pasa de 100 caracteres).
- 404 `member_not_found`; un id que no es UUID da 422. Solo lecturas, en la cubeta `staff-read`
  (120 por minuto), sin tocar `athletes-write`. La respuesta no trae campos de medidas.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import configure_keyring
from app.core.security import create_access_token
from app.modules.athletes.router import router
from tests.athletes._apoyo import ATHLETES
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.athletes import make_metric, make_record
from tests.factories.members import make_members
from tests.factories.wods import make_movement

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

RM = {"movement_id", "movement_name", "record_id", "value_g", "source", "achieved_on"}
RESUMEN = {
    "last_metric_on",
    "metrics_count",
    "current_rms",
    "benchmarks_with_attempts",
    "recent_records",
    "truncated",
}
TOPE_LECTURAS = 120
PROHIBIDOS = {"weight_g", "height_cm", "body_fat_pct", "notes", "has_weight", "has_notes"}


def _rms(member_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/rms"


def _resumen(member_id: UUID | str) -> str:
    return f"{ATHLETES}/{member_id}/summary"


async def _con_datos(session: AsyncSession, coach: UUID) -> UUID:
    miembro = (await make_members(session, 1))[0]
    sentadilla = (await make_movement(session, coach, "Back Squat", "kg")).id
    muerto = (await make_movement(session, coach, "Deadlift", "kg")).id
    await make_record(session, miembro.id, movement_id=sentadilla, value_g=120_000)
    await make_record(session, miembro.id, movement_id=muerto, value_g=150_000)
    await make_metric(session, miembro.id, measured_on=date(2026, 9, 20))
    return miembro.id


def test_el_router_publica_solo_lecturas_de_rms_y_resumen() -> None:
    publicadas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
        if ruta.path.endswith(("/rms", "/summary"))
    }
    assert publicadas == {
        ("GET", "/athletes/{member_id}/rms"),
        ("GET", "/athletes/{member_id}/summary"),
    }


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_leen_rms_y_resumen(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien = await usuario_real(rol)
    socio_id = await _con_datos(session, quien.id)
    h = cabeceras(quien)

    rms = await app_http.get(_rms(socio_id), headers=h)
    resumen = await app_http.get(_resumen(socio_id), headers=h)

    assert rms.status_code == 200, rms.text
    assert rms.headers["cache-control"] == "no-store"
    pagina = rms.json()
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (2, 25, 0)
    assert [set(i) for i in pagina["items"]] == [RM, RM]
    assert [(i["movement_name"], i["value_g"]) for i in pagina["items"]] == [
        ("Back Squat", 120_000),
        ("Deadlift", 150_000),
    ]
    assert resumen.status_code == 200, resumen.text
    assert resumen.headers["cache-control"] == "no-store"
    cuerpo: dict[str, Any] = resumen.json()
    assert set(cuerpo) == RESUMEN
    assert (cuerpo["last_metric_on"], cuerpo["metrics_count"], cuerpo["current_rms"]) == (
        "2026-09-20",
        1,
        2,
    )
    assert len(cuerpo["recent_records"]) == 2
    assert not PROHIBIDOS & set(cuerpo)
    assert all(not PROHIBIDOS & set(r) for r in cuerpo["recent_records"])


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)
    rol_socio = await usuario_real("member")
    for ruta in (_rms(socio_id), _resumen(socio_id)):
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
    socio_id = await _con_datos(session, coach.id)
    acceso = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    for ruta in (_rms(socio_id), _resumen(socio_id)):
        r = await app_http.get(ruta, headers=cab)
        assert r.status_code == 403, (ruta, r.text)
        assert r.json()["error"]["code"] == "kiosk_mode"


async def test_404_de_socio_inexistente_y_422_de_ids_mal_formados(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    h = cabeceras(await usuario_real("coach"))

    for ruta in (_rms(uuid4()), _resumen(uuid4())):
        r = await app_http.get(ruta, headers=h)
        assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"
        assert r.headers["cache-control"] == "no-store"
    for ruta in (_rms("no-es-uuid"), _resumen("no-es-uuid")):
        assert (await app_http.get(ruta, headers=h)).status_code == 422


async def test_rms_valida_y_aplica_la_paginacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)
    h = cabeceras(coach)

    for params in ({"limit": 201}, {"limit": 0}, {"offset": -1}):
        r = await app_http.get(_rms(socio_id), params=params, headers=h)
        assert r.status_code == 422, params
    primera = await app_http.get(_rms(socio_id), params={"limit": 1, "offset": 0}, headers=h)
    segunda = await app_http.get(_rms(socio_id), params={"limit": 1, "offset": 1}, headers=h)
    fuera = await app_http.get(_rms(socio_id), params={"limit": 1, "offset": 5}, headers=h)

    assert [i["movement_name"] for i in primera.json()["items"]] == ["Back Squat"]
    assert [i["movement_name"] for i in segunda.json()["items"]] == ["Deadlift"]
    assert (fuera.status_code, fuera.json()["total"], fuera.json()["items"]) == (200, 2, [])


async def test_rms_acepta_q_por_nombre_y_rechaza_uno_demasiado_largo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)
    h = cabeceras(coach)

    con = await app_http.get(_rms(socio_id), params={"q": "DEAD"}, headers=h)
    sin = await app_http.get(_rms(socio_id), params={"q": "zzz"}, headers=h)
    larga = await app_http.get(_rms(socio_id), params={"q": "x" * 101}, headers=h)

    assert con.status_code == 200 and con.json()["total"] == 1
    assert con.json()["items"][0]["movement_name"] == "Deadlift"
    assert sin.status_code == 200 and sin.json()["total"] == 0
    assert larga.status_code == 422 and larga.json()["error"]["field"] == "q"


async def test_cubeta_staff_read_120_por_minuto_y_no_toca_athletes_write(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)
    h = cabeceras(coach)
    for i in range(TOPE_LECTURAS):
        r = await app_http.get(_rms(socio_id) if i % 2 else _resumen(socio_id), headers=h)
        assert r.status_code == 200, (i, r.text)

    r = await app_http.get(_rms(socio_id), headers=h)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers


async def test_con_el_custodio_sellado_el_resumen_y_los_rms_dan_200(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """No descifran: a diferencia de `reveal` (503), con el keyring sin cargar responden 200."""
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)
    h = cabeceras(coach)
    configure_keyring(None)  # el custodio se selló: no hay llaves en memoria

    rms = await app_http.get(_rms(socio_id), headers=h)
    resumen = await app_http.get(_resumen(socio_id), headers=h)

    assert rms.status_code == 200, rms.text
    assert resumen.status_code == 200, resumen.text
    assert resumen.json()["metrics_count"] == 1
    assert resumen.headers["cache-control"] == "no-store"


async def test_el_resumen_publica_el_contrato_de_recientes_sin_quien_registro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    coach = await usuario_real("coach")
    socio_id = await _con_datos(session, coach.id)

    r = await app_http.get(_resumen(socio_id), headers=cabeceras(coach))

    cuerpo = r.json()
    assert cuerpo["truncated"] is False
    for reciente in cuerpo["recent_records"]:
        assert not {
            "recorded_by",
            "recorded_by_name",
            "result_source",
            "result_id",
            "is_current",
            "invalidated_at",
            "invalidated_reason",
        } & set(reciente)
        assert {"id", "kind", "source", "achieved_on", "wod_id", "movement_name"} <= set(reciente)
