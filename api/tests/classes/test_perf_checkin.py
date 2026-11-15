"""Rendimiento del check-in (S7-V6, US-159). Marcado `perf`: no es gate.

`POST /attendance` con 1.000 socios y una sesión que ya tiene 15 asistentes (cupo 15): cada
registro, el 16 en adelante con `over_capacity`, tarda menos de 2 s en varias ejecuciones. El
puerto de membresías es el doble de `tests/classes/conftest.py` (la parte de `memberships` se
mide con los E2E y el check-in real de V8).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import FakeMembershipPort, make_attendance, make_session
from tests.factories.members import make_members

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

RUTA = "/api/v1/attendance"
SOCIOS = 1000
ASISTENTES = 15
EJECUCIONES = 6
LIMITE_MS = 2000
EN_VENTANA = datetime(2026, 10, 21, 15, 10, tzinfo=UTC)


async def test_checkin_con_mil_socios_y_quince_asistentes_bajo_2_s(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    puerto: FakeMembershipPort,
) -> None:
    socios = await make_members(session, SOCIOS, last_name="Carga")
    clase = await make_session(session, starts_at=EN_VENTANA)
    for socio in socios[:ASISTENTES]:
        await make_attendance(session, clase, socio.id)
    # ANALYZE tras sembrar: la siembra queda sin confirmar y PG planearia con tablas vacias.
    await session.execute(text("ANALYZE classes.attendance"))
    await session.execute(text("ANALYZE classes.class_sessions"))
    await session.execute(text("ANALYZE members.members"))
    admin = await usuario_real("admin")
    cab = cabeceras(admin)

    tiempos: list[float] = []
    for socio in socios[ASISTENTES : ASISTENTES + EJECUCIONES]:
        cuerpo = {"session_id": str(clase.id), "member_id": str(socio.id)}
        inicio = time.perf_counter()
        r = await app_http.post(RUTA, json=cuerpo, headers=cab)
        tiempos.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 201, r.text
        assert "over_capacity" in r.json()["flags"]
    print(f"check-in con {SOCIOS} socios, ms por ejecucion: {[round(t) for t in tiempos]}")
    assert all(ms < LIMITE_MS for ms in tiempos), [f"{ms:.0f} ms" for ms in tiempos]
