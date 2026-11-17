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

from sqlalchemy import and_, select
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


@dataclass(frozen=True, slots=True)
class WodTitle:
    """Lo que las lecturas de `results` piden de un WOD (S8-B4): título, fecha y tipo de marca."""

    wod_id: UUID
    title: str
    date: date
    score_type: str
    benchmark_id: UUID | None


async def today_title(session: AsyncSession, day: date) -> WodTitle | None:
    """El WOD de `day` en cinco columnas (S8-C1b, rendimiento de B5): sin movimientos, benchmark
    ni conteo de resultados. Lo usa la tarjeta del tablero."""
    fila = (
        await session.execute(
            select(Wod.id, Wod.title, Wod.date, Wod.score_type, Wod.benchmark_id).where(
                Wod.date == day
            )
        )
    ).first()
    if fila is None:
        return None
    return WodTitle(fila.id, fila.title, fila.date, fila.score_type, fila.benchmark_id)


async def titles_for(session: AsyncSession, wod_ids: Collection[UUID]) -> dict[UUID, WodTitle]:
    """El título de cada WOD existente, en UNA consulta y sin candados (lectura)."""
    if not wod_ids:
        return {}
    filas = await session.execute(
        select(Wod.id, Wod.title, Wod.date, Wod.score_type, Wod.benchmark_id).where(
            Wod.id.in_(set(wod_ids))
        )
    )
    return {f.id: WodTitle(f.id, f.title, f.date, f.score_type, f.benchmark_id) for f in filas}


# S9-B1 (S9-D6, S9-D9, US-180): lecturas del catálogo para `athletes` ----------------------------


@dataclass(frozen=True, slots=True)
class MovementRef:
    """Un movimiento del catálogo como dato plano (un service no entrega ORM a otro módulo)."""

    id: UUID
    name: str
    unit: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class BenchmarkRef:
    """Un benchmark del catálogo como dato plano."""

    id: UUID
    name: str
    score_type: str


async def movement_refs(session: AsyncSession, ids: Collection[UUID]) -> dict[UUID, MovementRef]:
    """Nombre, unidad y estado de cada movimiento existente, en UNA consulta y SIN candados."""
    if not ids:
        return {}
    filas = await session.execute(
        select(Movement.id, Movement.name, Movement.unit, Movement.is_active).where(
            Movement.id.in_(set(ids))
        )
    )
    return {f.id: MovementRef(f.id, f.name, f.unit, f.is_active) for f in filas}


async def benchmark_refs(session: AsyncSession, ids: Collection[UUID]) -> dict[UUID, BenchmarkRef]:
    """Nombre y tipo de marca de cada benchmark existente, en UNA consulta y SIN candados."""
    if not ids:
        return {}
    filas = await session.execute(
        select(Benchmark.id, Benchmark.name, Benchmark.score_type).where(Benchmark.id.in_(set(ids)))
    )
    return {f.id: BenchmarkRef(f.id, f.name, f.score_type) for f in filas}


# S9-B3 (S9-D6, US-181): lo que el handler de `athletes` pide de un WOD ---------------------------


@dataclass(frozen=True, slots=True)
class WodRecordMeta:
    """Tipo de marca, movimiento principal, benchmark y fecha de un WOD como dato plano."""

    score_type: str
    primary_movement_id: UUID | None
    benchmark_id: UUID | None
    date: date


async def record_meta_for(
    session: AsyncSession, wod_ids: Collection[UUID]
) -> dict[UUID, WodRecordMeta]:
    """Por lote y SIN candado (el handler suscrito no pide candados, S9-D7; `scoring_for` toma
    `FOR SHARE` y es de un solo WOD): los WODs existentes por id, en UNA consulta con el principal
    (`LEFT JOIN` a `wod_movements` con `is_primary`, a lo sumo uno por WOD). Los ausentes faltan."""
    if not wod_ids:
        return {}
    filas = await session.execute(
        select(Wod.id, Wod.score_type, Wod.benchmark_id, Wod.date, WodMovement.movement_id)
        .outerjoin(WodMovement, and_(WodMovement.wod_id == Wod.id, WodMovement.is_primary))
        .where(Wod.id.in_(set(wod_ids)))
    )
    return {
        f.id: WodRecordMeta(
            score_type=f.score_type,
            primary_movement_id=f.movement_id,
            benchmark_id=f.benchmark_id,
            date=f.date,
        )
        for f in filas
    }
