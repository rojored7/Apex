"""Lecturas de catálogo para los WODs (S8-A3). Privado del módulo: lo usa `programming.py`.

- `movements_by_id(session, ids)`: los movimientos del catálogo por id (una consulta), con
  `FOR SHARE` y datos frescos: un `PATCH /movements` concurrente (que los bloquea `FOR UPDATE`)
  espera a que el WOD confirme y luego ve el uso (revisión de A4, M-1).
- `ensure_wod`, `day_wod_ids` y `wod_date` (S8-A4, S8-D9): lo que `classes` pide por `service.py`.
- `benchmark_for_share(session, benchmark_id)`: el benchmark con `FOR SHARE`,
  para que un `PATCH /benchmarks/{id}` del `score_type` concurrente espere a que el WOD confirme.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods.exceptions import WodNotFound, WodsValidationError
from app.modules.wods.models import Benchmark, Movement, Wod, WodMovement


async def movements_by_id(session: AsyncSession, ids: Sequence[UUID]) -> dict[UUID, Movement]:
    if not ids:
        return {}
    filas = await session.scalars(
        select(Movement)
        .where(Movement.id.in_(set(ids)))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return {m.id: m for m in filas}


async def benchmark_for_share(session: AsyncSession, benchmark_id: UUID) -> Benchmark | None:
    """Lee el benchmark con `FOR SHARE` y datos frescos (`populate_existing`): el `score_type`
    que se compara es el confirmado y nadie lo cambia hasta que este WOD confirme."""
    return await session.scalar(
        select(Benchmark)
        .where(Benchmark.id == benchmark_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )


async def ensure_wod(session: AsyncSession, wod_id: UUID) -> None:
    """El WOD existe; si no, 422 con `field = "wod_id"` (S8-D9). Un WOD no se borra (RN-14)."""
    if await session.scalar(select(Wod.id).where(Wod.id == wod_id)) is None:
        raise WodsValidationError(message="El WOD no existe.", field="wod_id")


async def day_wod_ids(session: AsyncSession, dates: Collection[date]) -> dict[date, UUID]:
    """El WOD de cada fecha pedida (las fechas sin WOD faltan), en UNA consulta (S8-D9)."""
    if not dates:
        return {}
    filas = await session.execute(select(Wod.date, Wod.id).where(Wod.date.in_(set(dates))))
    return {dia: wod_id for dia, wod_id in filas.all()}


async def wod_date(session: AsyncSession, wod_id: UUID) -> date | None:
    """La fecha de un WOD, o `None` si no existe (S8-D9)."""
    return await session.scalar(select(Wod.date).where(Wod.id == wod_id))


@dataclass(frozen=True, slots=True)
class WodScoring:
    """Lo que `results` necesita de un WOD para validar una marca (S8-D36)."""

    wod_id: UUID
    date: date
    score_type: str
    time_cap_s: int | None
    benchmark_id: UUID | None
    movement_ids: frozenset[UUID]
    primary_movement_id: UUID | None


async def scoring_for(session: AsyncSession, wod_id: UUID) -> WodScoring:
    """El WOD con `FOR SHARE` y datos frescos (S8-D36, M-6): un `PATCH /wods` concurrente espera a
    que el resultado confirme. `WodNotFound` (404) si no existe."""
    wod = await session.scalar(
        select(Wod)
        .where(Wod.id == wod_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if wod is None:
        raise WodNotFound()
    filas = await session.execute(
        select(WodMovement.movement_id, WodMovement.is_primary).where(WodMovement.wod_id == wod_id)
    )
    pares = filas.all()
    return WodScoring(
        wod_id=wod.id,
        date=wod.date,
        score_type=wod.score_type,
        time_cap_s=wod.time_cap_s,
        benchmark_id=wod.benchmark_id,
        movement_ids=frozenset(m for m, _ in pares),
        primary_movement_id=next((m for m, principal in pares if principal), None),
    )
