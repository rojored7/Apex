"""Rendimiento del resumen de 26 semanas (S7-R1, M-5). Marcado `perf`: no es gate.

Siembra 26 semanas de sesiones (3 por semana, cupo 15) con asistencias y mide el resumen:
agregado en SQL, bajo 500 ms tras un calentamiento.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes import service
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "bus_listo")]

LUNES = date(2026, 4, 27)


async def test_resumen_de_26_semanas_bajo_500_ms(session: AsyncSession) -> None:
    socios = await make_members(session, 15)
    inicio = datetime(2026, 4, 27, 11, 0, tzinfo=UTC)
    for semana in range(26):
        for franja in range(3):
            clase = await make_session(
                session, starts_at=inicio + timedelta(weeks=semana, hours=franja * 3)
            )
            for socio in socios[: 5 + franja * 3]:
                await make_attendance(session, clase, socio.id)
    hasta = LUNES + timedelta(days=7 * 26 - 1)
    await service.attendance_summary(session, LUNES, hasta)  # calentamiento
    t0 = time.perf_counter()
    resumen = await service.attendance_summary(session, LUNES, hasta)
    ms = (time.perf_counter() - t0) * 1000
    assert len(resumen.weeks) == 26 and resumen.weeks[0].total > 0
    assert ms < 500, f"{ms:.0f} ms"
