"""Lecturas de catálogo para los WODs (S8-A3). Privado del módulo: lo usa `programming.py`.

- `movements_by_id(session, ids)`: los movimientos del catálogo por id (una consulta).
- `benchmark_for_share(session, benchmark_id)`: el benchmark con `FOR SHARE`,
  para que un `PATCH /benchmarks/{id}` del `score_type` concurrente espere a que el WOD confirme.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods.models import Benchmark, Movement


async def movements_by_id(session: AsyncSession, ids: Sequence[UUID]) -> dict[UUID, Movement]:
    if not ids:
        return {}
    filas = await session.scalars(select(Movement).where(Movement.id.in_(set(ids))))
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
