"""Job `generate_sessions` (S7-B1, US-156; S7-D10). Rojo B1.

Por `runner.run_job` con el `JobSpec` real de `JOBS` y commit real. Hoy (`reloj_worker`) es el 21 de
octubre de 2026: una franja de lunes crea el 26 de octubre y el 2 de noviembre.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.jobs import DETAIL_KEYS
from app.worker import runner
from app.worker.jobs import JOBS, generate_sessions
from tests.conftest import LIMPIAR_CLASS_SESSIONS, LIMPIAR_CLASS_SLOTS
from tests.factories.classes import make_slot

Fabrica = async_sessionmaker[AsyncSession]
SPEC = next(s for s in JOBS if s.name == generate_sessions.NAME)


@pytest.fixture(autouse=True)
async def _limpiar(session_factory: Fabrica):  # type: ignore[no-untyped-def]
    yield
    async with session_factory() as sesion:
        await sesion.execute(text(LIMPIAR_CLASS_SESSIONS))
        await sesion.execute(text(LIMPIAR_CLASS_SLOTS))
        await sesion.commit()


async def _contar(fabrica: Fabrica) -> int:
    async with fabrica() as sesion:
        return int(await sesion.scalar(text("SELECT count(*) FROM classes.class_sessions")) or 0)


async def test_el_job_esta_registrado_con_300_segundos_y_sin_cifrado() -> None:
    assert (SPEC.hour, SPEC.minute, SPEC.timeout_s) == (7, 0, 300)
    assert SPEC.crypto_classes == frozenset()
    assert {"creadas", "franjas"} <= DETAIL_KEYS


async def test_crea_las_sesiones_y_reporta_solo_enteros(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    async with session_factory() as sesion:
        await make_slot(sesion, weekdays=[0])
    salida = await runner.run_job(SPEC, clock=reloj_worker, session_factory=session_factory)
    assert salida.result == "ok"
    assert salida.details == {"creadas": 2, "franjas": 1}
    assert await _contar(session_factory) == 2


async def test_dos_corridas_el_mismo_dia_no_duplican(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    async with session_factory() as sesion:
        await make_slot(sesion, weekdays=[0])
    await runner.run_job(SPEC, clock=reloj_worker, session_factory=session_factory)
    segunda = await runner.run_job(SPEC, clock=reloj_worker, session_factory=session_factory)
    assert segunda.result == "ok" and segunda.details == {"creadas": 0, "franjas": 1}
    assert await _contar(session_factory) == 2


async def test_las_filas_van_a_nombre_del_usuario_del_sistema(
    session_factory: Fabrica, reloj_worker: FrozenClock
) -> None:
    async with session_factory() as sesion:
        await make_slot(sesion, weekdays=[0])
    await runner.run_job(SPEC, clock=reloj_worker, session_factory=session_factory)
    async with session_factory() as sesion:
        autores = (
            (await sesion.execute(text("SELECT DISTINCT created_by FROM classes.class_sessions")))
            .scalars()
            .all()
        )
    assert list(autores) == [SYSTEM_USER_ID]
