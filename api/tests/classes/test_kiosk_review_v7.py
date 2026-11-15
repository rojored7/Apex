"""Correcciones de la revisión final del backend (S7-V7b). Rojo V7b.

- M-1: con la marca de quiosco, `GET /class-sessions/{id}` y `POST /attendance` aplican la ventana
  hoy o ayer de S7-D42 (403 `kiosk_mode`); sin la marca no hay ventana.
- M-2: con la marca, `GET /attendance?q=` busca solo por nombre (nunca por documento, teléfono o
  correo, que serían un oráculo).
- L-2: la regla «hoy o ayer» es una sola función pura de `classes.rules`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token
from app.modules.classes import rules
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.notifications._apoyo_avisos import socio

SESIONES = "/api/v1/class-sessions"
ASISTENCIAS = "/api/v1/attendance"
HOY = datetime(2026, 10, 21, 11, 0, tzinfo=UTC)
AYER = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)
HACE_3_DIAS = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _quiosco(user: Any, reloj: FrozenClock) -> dict[str, str]:
    token = create_access_token(user.id, "coach", None, reloj, kiosk=True)
    return {"Authorization": f"Bearer {token}", "Origin": ORIGEN}


def test_la_regla_hoy_o_ayer_es_una_sola_funcion_pura() -> None:
    hoy = date(2026, 10, 21)
    assert rules.is_kiosk_day(hoy, hoy) and rules.is_kiosk_day(date(2026, 10, 20), hoy)
    assert not rules.is_kiosk_day(date(2026, 10, 19), hoy)
    assert not rules.is_kiosk_day(date(2026, 10, 22), hoy)
    assert rules.is_other_day(date(2026, 10, 19), hoy) is True
    assert rules.is_other_day(hoy, hoy) is False


async def test_en_quiosco_el_detalle_de_una_sesion_vieja_da_403_y_el_de_hoy_y_ayer_no(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    vieja = await make_session(session, starts_at=HACE_3_DIAS)
    de_hoy = await make_session(session, starts_at=HOY)
    de_ayer = await make_session(session, starts_at=AYER)
    ids = (vieja.id, de_hoy.id, de_ayer.id)
    quiosco = _quiosco(coach, reloj)
    r = await app_http.get(f"{SESIONES}/{ids[0]}", headers=quiosco)
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
    for ok in ids[1:]:
        assert (await app_http.get(f"{SESIONES}/{ok}", headers=quiosco)).status_code == 200
    normal = await app_http.get(f"{SESIONES}/{ids[0]}", headers=cabeceras(coach))
    assert normal.status_code == 200, normal.text


async def test_en_quiosco_no_se_registra_asistencia_en_una_sesion_vieja_ni_inexistente(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    vieja = await make_session(session, starts_at=HACE_3_DIAS)
    miembro = await socio(session)
    vieja_id, miembro_id = vieja.id, miembro.id
    quiosco = _quiosco(coach, reloj)
    r = await app_http.post(
        ASISTENCIAS,
        json={"session_id": str(vieja_id), "member_id": str(miembro_id)},
        headers=quiosco,
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text
    nula = "00000000-0000-0000-0000-0000000000aa"
    r = await app_http.post(
        ASISTENCIAS, json={"session_id": nula, "member_id": str(miembro_id)}, headers=quiosco
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text


async def test_en_quiosco_si_se_registra_asistencia_en_una_sesion_de_hoy(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    clase = await make_session(session, starts_at=HOY)
    miembro = await socio(session)
    r = await app_http.post(
        ASISTENCIAS,
        json={"session_id": str(clase.id), "member_id": str(miembro.id)},
        headers=_quiosco(coach, reloj),
    )
    assert r.status_code == 201, r.text


async def test_en_quiosco_q_de_asistencias_no_busca_por_correo_y_sin_quiosco_si(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    clase = await make_session(session, starts_at=HOY)
    miembro = await socio(session, email="oraculo.v7@test.apex")
    await make_attendance(session, clase, miembro.id, membership_status_at_checkin="none")
    url = f"{ASISTENCIAS}?session_id={clase.id}&q=oraculo.v7@test.apex"
    r = await app_http.get(url, headers=_quiosco(coach, reloj))
    assert r.status_code == 200 and r.json()["items"] == [], r.text
    normal = await app_http.get(url, headers=cabeceras(coach))
    assert len(normal.json()["items"]) == 1, normal.text
    por_nombre = await app_http.get(
        f"{ASISTENCIAS}?session_id={clase.id}&q=Luc", headers=_quiosco(coach, reloj)
    )
    assert len(por_nombre.json()["items"]) == 1, por_nombre.text
