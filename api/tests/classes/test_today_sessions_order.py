"""`today_sessions`: las canceladas al final y el tope de 50 nunca deja fuera una viva (S8-B5,
S8-D25)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.modules.classes import service as classes_service
from tests.factories.classes import make_session

MARTES = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
SEIS, DOCE, DIECIOCHO = (datetime(2026, 10, 20, h, 0, tzinfo=UTC) for h in (11, 17, 23))

pytestmark = pytest.mark.usefixtures("bus_listo")


@pytest.fixture(autouse=True)
def _martes(reloj: FrozenClock) -> None:
    reloj.set(MARTES)


async def _cancelada(session: AsyncSession, starts_at: datetime) -> None:
    await make_session(
        session,
        starts_at=starts_at,
        status="cancelled",
        cancel_reason="lluvia",
        cancelled_by=SYSTEM_USER_ID,
        cancelled_at=MARTES,
    )


async def test_canceladas_al_final(session: AsyncSession) -> None:
    await _cancelada(session, SEIS)
    await make_session(session, starts_at=DOCE)
    await make_session(session, starts_at=DIECIOCHO)
    await _cancelada(session, DOCE + timedelta(hours=1))
    sesiones = await classes_service.today_sessions(session, MARTES.date())
    assert [s.status for s in sesiones] == ["scheduled", "scheduled", "cancelled", "cancelled"]
    assert [s.starts_at for s in sesiones[:2]] == [DOCE, DIECIOCHO]
    assert [s.starts_at for s in sesiones[2:]] == [SEIS, DOCE + timedelta(hours=1)]


async def test_tope_50_nunca_deja_fuera_una_viva(session: AsyncSession) -> None:
    for minuto in range(50):
        await _cancelada(session, SEIS + timedelta(minutes=minuto))
    viva = await make_session(session, starts_at=DIECIOCHO)
    sesiones = await classes_service.today_sessions(session, MARTES.date())
    assert len(sesiones) == classes_service.TODAY_SESSIONS_LIMIT == 50
    assert sesiones[0].id == viva.id and sesiones[0].status == "scheduled"
