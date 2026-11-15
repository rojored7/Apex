"""`attendance_week` y `sessions_today` del tablero (S7-R3, US-164; S7-D16). Rojo R3.

Martes 20 de octubre de 2026, 10:00 de Bogotá, con sesiones a las 06:00, 12:00 y 18:00.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.modules.classes import service as classes_service
from tests.dashboard.conftest import dashboard_service
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members
from tests.factories.users import make_user

MARTES = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
SEIS, DOCE, DIECIOCHO = (datetime(2026, 10, 20, h, 0, tzinfo=UTC) for h in (11, 17, 23))
LLEGADA = MARTES - timedelta(hours=1)

pytestmark = pytest.mark.usefixtures("bus_listo")


@pytest.fixture(autouse=True)
def _martes(reloj: FrozenClock) -> None:
    reloj.set(MARTES)


async def test_martes_tres_clases_41_y_3_marcadas(session: AsyncSession) -> None:
    clases = [await make_session(session, starts_at=h) for h in (SEIS, DOCE, DIECIOCHO)]
    socios = await make_members(session, 41)
    for i, socio in enumerate(socios):
        flags = ["expired"] if i < 3 else []
        await make_attendance(session, clases[i % 3], socio.id, flags=flags, checked_in_at=LLEGADA)
    # No cuentan: la del domingo anterior y una quitada (de un socio con otra clase viva).
    domingo = await make_session(session, starts_at=datetime(2026, 10, 18, 15, 0, tzinfo=UTC))
    await make_attendance(session, domingo, socios[0].id)
    await make_attendance(
        session,
        clases[1],
        socios[0].id,
        removed_at=MARTES,
        removed_reason="x",
        checked_in_at=LLEGADA,
    )
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.attendance_week.count == 41
    assert tablero.attendance_week.flagged_count == 3
    assert [s.starts_at for s in tablero.sessions_today] == [SEIS, DOCE, DIECIOCHO]
    assert [s.attendance_count for s in tablero.sessions_today] == [14, 14, 13]
    assert [s.status for s in tablero.sessions_today] == ["done", "scheduled", "scheduled"]
    assert all(s.capacity == 15 and s.coach_name is None for s in tablero.sessions_today)


async def test_dia_sin_clases_lista_vacia(session: AsyncSession) -> None:
    await make_session(session, starts_at=SEIS + timedelta(days=1))
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.sessions_today == []
    assert tablero.attendance_week.count == 0 and tablero.attendance_week.flagged_count == 0


async def test_maximo_50(session: AsyncSession) -> None:
    for minuto in range(55):
        await make_session(session, starts_at=SEIS + timedelta(minutes=minuto))
    sesiones = await classes_service.today_sessions(session, MARTES.date())
    assert len(sesiones) == classes_service.TODAY_SESSIONS_LIMIT == 50
    assert sesiones == sorted(sesiones, key=lambda s: s.starts_at)


async def test_la_cancelada_sale_con_su_estado(session: AsyncSession) -> None:
    await make_session(
        session,
        starts_at=DOCE,
        status="cancelled",
        cancel_reason="lluvia",
        cancelled_by=SYSTEM_USER_ID,
        cancelled_at=MARTES,
    )
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert [s.status for s in tablero.sessions_today] == ["cancelled"]


# S7-C4d (L-4, L-5) -------------------------------------------------------------------------------


def test_el_tope_del_tablero_es_el_de_classes() -> None:
    """L-4: `dashboard.schemas` no importa `classes`; las dos constantes no pueden divergir."""
    from app.modules.dashboard.schemas import SESSIONS_TODAY_LIMIT

    assert SESSIONS_TODAY_LIMIT == classes_service.TODAY_SESSIONS_LIMIT


async def test_el_nombre_del_coach_sale_por_lote_y_distinto_en_cada_sesion(
    session: AsyncSession,
) -> None:
    ana = await make_user(session, role="coach", email="ana.coach@test.apex")
    luis = await make_user(session, role="coach", email="luis.coach@test.apex")
    await make_session(session, starts_at=SEIS, coach_id=ana.id)
    await make_session(session, starts_at=DOCE, coach_id=luis.id)
    await make_session(session, starts_at=DIECIOCHO)
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert [s.coach_name for s in tablero.sessions_today] == [
        "ana.coach",
        "luis.coach",
        None,
    ]


async def test_el_domingo_23_30_de_bogota_no_cuenta_en_la_semana_nueva(
    session: AsyncSession,
) -> None:
    """Lunes 19 00:00 Bogotá = 05:00Z. 04:30Z del lunes es domingo 23:30 en Bogotá: semana vieja."""
    socios = await make_members(session, 3)
    domingo_noche = datetime(2026, 10, 19, 4, 30, tzinfo=UTC)
    lunes_cero = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)
    clase = await make_session(session, starts_at=SEIS)
    await make_attendance(session, clase, socios[0].id, checked_in_at=domingo_noche)
    await make_attendance(session, clase, socios[1].id, checked_in_at=lunes_cero)
    await make_attendance(session, clase, socios[2].id, checked_in_at=LLEGADA)
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.attendance_week.count == 2


async def test_cada_sesion_del_tablero_trae_duration_min_de_la_sesion(
    session: AsyncSession,
) -> None:
    """V7 (L-12 del front): `duration_min` es el dato de la sesión, no un valor fijo."""
    await make_session(session, starts_at=SEIS, duration_min=45)
    await make_session(session, starts_at=DOCE, duration_min=90)
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert [s.duration_min for s in tablero.sessions_today] == [45, 90]
