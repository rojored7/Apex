"""`wod_today` del tablero como objeto propio (S8-B5, US-174; S8-D16). El día es el de Bogotá."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.dashboard.schemas import WodTodayOut
from tests.dashboard.conftest import dashboard_service
from tests.factories.users import make_user
from tests.factories.wods import make_benchmark, make_movement, make_wod

pytestmark = pytest.mark.usefixtures("bus_listo")

MARTES = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


async def test_objeto_con_id_title_score_type_is_benchmark(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    reloj.set(MARTES)
    admin = await make_user(session, role="admin", email="wod.admin@test.apex")
    mov = await make_movement(session, admin.id)
    bench = await make_benchmark(session, admin.id, "Fran")
    wod = await make_wod(
        session, admin.id, [mov.id], date="2026-10-20", title="Fran", benchmark_id=bench.id
    )
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.wod_today == WodTodayOut(
        id=wod.id, title="Fran", score_type="time", is_benchmark=True
    )
    assert set(tablero.wod_today.model_dump()) == {"id", "title", "score_type", "is_benchmark"}
    assert set(tablero.model_dump(mode="json")["wod_today"]) == {
        "id",
        "title",
        "score_type",
        "is_benchmark",
    }


async def test_wod_sin_benchmark_no_es_benchmark(session: AsyncSession, reloj: FrozenClock) -> None:
    reloj.set(MARTES)
    admin = await make_user(session, role="admin", email="wod.admin2@test.apex")
    mov = await make_movement(session, admin.id)
    await make_wod(
        session,
        admin.id,
        [mov.id],
        date="2026-10-20",
        title="Libre",
        score_type="reps",
        time_cap_s=None,
    )
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.wod_today is not None
    assert tablero.wod_today.is_benchmark is False
    assert tablero.wod_today.score_type == "reps"


async def test_null_sin_wod(session: AsyncSession, reloj: FrozenClock) -> None:
    reloj.set(MARTES)
    admin = await make_user(session, role="admin", email="wod.admin3@test.apex")
    mov = await make_movement(session, admin.id)
    await make_wod(session, admin.id, [mov.id], date="2026-10-21", title="Mañana")
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.wod_today is None
    assert tablero.model_dump(mode="json")["wod_today"] is None


async def test_01_00_utc_es_el_wod_de_bogota(session: AsyncSession, reloj: FrozenClock) -> None:
    """01:00Z del 22 son las 20:00 del 21 en Bogotá: el WOD de hoy es el del 21 (CA3)."""
    reloj.set(datetime(2026, 10, 22, 1, 0, tzinfo=UTC))
    admin = await make_user(session, role="admin", email="wod.admin4@test.apex")
    mov = await make_movement(session, admin.id)
    await make_wod(session, admin.id, [mov.id], date="2026-10-21", title="Ayer UTC")
    await make_wod(session, admin.id, [mov.id], date="2026-10-22", title="Hoy UTC")
    tablero = await dashboard_service.summary(session, with_finances=False)
    assert tablero.wod_today is not None
    assert tablero.wod_today.title == "Ayer UTC"


async def test_tarjeta_liviana_sin_movimientos_ni_resultados(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    """Rendimiento (revisión de B5, S8-C1b): la tarjeta lee solo cuatro columnas de `wods.wods`;
    ni `wod_movements`, ni `benchmarks`, ni `results` entran en el tablero."""
    from sqlalchemy import event

    reloj.set(MARTES)
    admin = await make_user(session, role="admin", email="wod.admin5@test.apex")
    mov = await make_movement(session, admin.id)
    await make_wod(session, admin.id, [mov.id], date="2026-10-20", title="Liviano")
    sobre_wods: list[str] = []

    def _anota(conn: object, cursor: object, statement: str, *args: object) -> None:
        texto = statement.lower()
        if "wods.wods" in texto or "wods.wod_movements" in texto or "results." in texto:
            sobre_wods.append(texto)

    motor = session.get_bind()
    event.listen(motor, "before_cursor_execute", _anota)
    try:
        tablero = await dashboard_service.summary(session, with_finances=False)
    finally:
        event.remove(motor, "before_cursor_execute", _anota)
    assert tablero.wod_today is not None and tablero.wod_today.title == "Liviano"
    assert len(sobre_wods) == 1, sobre_wods
    assert "wod_movements" not in sobre_wods[0] and "benchmarks" not in sobre_wods[0]
    assert "wods.wods.description" not in sobre_wods[0]
