"""Rendimiento del tablero con clases (S7-R3, US-164 criterio 5). Marcada `perf`.

1.000 socios y 20.000 asistencias en los últimos días: `dashboard.service.summary` en menos de
300 ms (mediana de 5, tras un calentamiento).
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from tests.dashboard.conftest import dashboard_service
from tests.factories.classes import make_session
from tests.factories.members import make_members

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("bus_listo")]

MARTES = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
LIMITE_MS = 300


async def test_tablero_con_clases_bajo_300_ms(session: AsyncSession, reloj: FrozenClock) -> None:
    reloj.set(MARTES)
    await make_members(session, 1000, last_name="Carga")
    clases = [
        await make_session(session, starts_at=MARTES - timedelta(hours=4, days=d))
        for d in range(20)
    ]
    await session.execute(
        text(
            "INSERT INTO classes.attendance (id, session_id, member_id, membership_id, "
            "membership_status_at_checkin, flags, checked_in_at, checked_in_by, created_by, "
            "created_at, updated_at) "
            "SELECT gen_random_uuid(), cs.id, m.id, gen_random_uuid(), 'active', "
            "ARRAY[]::text[], cs.starts_at, :u, :u, now(), now() "
            "FROM classes.class_sessions cs CROSS JOIN members.members m "
            "WHERE cs.id = ANY(CAST(:sids AS uuid[]))"
        ),
        {"u": SYSTEM_USER_ID, "sids": [str(c.id) for c in clases]},
    )
    await dashboard_service.summary(session, with_finances=True)
    tiempos = []
    for _ in range(5):
        inicio = time.perf_counter()
        await dashboard_service.summary(session, with_finances=True)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    ms = statistics.median(tiempos)
    print(f"tablero con clases y 20.000 asistencias: {ms:.0f} ms")
    assert ms < LIMITE_MS, f"{ms:.0f} ms"
