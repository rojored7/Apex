"""Catálogo de benchmarks (S8-A2, US-166, N-46; S8-D6). Privado del módulo: lo usa `service.py`.

- `create_benchmark(session, data, by)`: normaliza el nombre (la misma regla que los movimientos),
  rechaza el repetido con 409 `benchmark_exists` (`field = "name"`, `existing_id`); la carrera de
  dos altas la decide `uq_benchmarks_name_norm` dentro de un savepoint.
- `update_benchmark(session, benchmark_id, patch, by)`: `FOR UPDATE`, aplica solo lo enviado (`null`
  explícito da 422 con `field`); cambiar `score_type` con WODs que lo usan da 422
  `score_type_locked`. Sin cambios no hay `flush` ni auditoría.
- `get_benchmark` y `list_benchmarks(session, filters, page, q=)`: orden por nombre normalizado;
  `wod_counts` se pide UNA vez por página.
No hay borrado (RN-14; los triggers de la base también lo prohíben).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Text, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import violated_constraint
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.wods.exceptions import (
    BenchmarkExists,
    BenchmarkNotFound,
    ScoreTypeLocked,
    WodsValidationError,
)
from app.modules.wods.models import Benchmark
from app.modules.wods.rules import clean_movement_name, normalize_movement_name
from app.modules.wods.schemas import (
    BenchmarkCreate,
    BenchmarkListQuery,
    BenchmarkOut,
    BenchmarkPatch,
)

logger = logging.getLogger("app.wods")

UQ_NAME_NORM: Final = "uq_benchmarks_name_norm"
_EDITABLES: Final[tuple[str, ...]] = ("name", "description", "score_type")
_MENSAJE_NULO: Final = "Este campo no puede quedar vacío."


async def wod_counts(session: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
    """WODs que usan cada benchmark. En A2 no hay WODs: todos en 0 (A3 la reemplaza por la
    consulta agrupada sobre `wods.wods`, una por página)."""
    return dict.fromkeys(ids, 0)


def _out(bench: Benchmark, usos: dict[UUID, int]) -> BenchmarkOut:
    return BenchmarkOut.model_validate(
        {
            "id": bench.id,
            "name": bench.name,
            "description": bench.description,
            "score_type": bench.score_type,
            "wod_count": usos.get(bench.id, 0),
            "created_at": bench.created_at,
            "updated_at": bench.updated_at,
        }
    )


async def _outs(session: AsyncSession, benchs: list[Benchmark]) -> list[BenchmarkOut]:
    usos = await wod_counts(session, [b.id for b in benchs]) if benchs else {}
    return [_out(b, usos) for b in benchs]


async def _id_by_norm(session: AsyncSession, norm: str, *, exclude: UUID | None) -> UUID | None:
    consulta = select(Benchmark.id).where(Benchmark.name_norm == norm)
    if exclude is not None:
        consulta = consulta.where(Benchmark.id != exclude)
    return await session.scalar(consulta)


async def _guardar_unico(
    session: AsyncSession, norm: str, exclude: UUID | None, aplicar: Callable[[], None]
) -> None:
    """Aplica el cambio y hace `flush` DENTRO de un savepoint: `begin_nested()` vacía lo pendiente
    antes de abrirlo, así que el cambio se aplica ya dentro. El 23505 del índice único (la
    carrera de dos altas) es 409 `benchmark_exists` y la sesión sigue usable (S8-A1b)."""
    try:
        async with session.begin_nested():
            aplicar()
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != UQ_NAME_NORM:
            raise
        raise BenchmarkExists(await _id_by_norm(session, norm, exclude=exclude)) from None


async def create_benchmark(session: AsyncSession, data: BenchmarkCreate, by: UUID) -> BenchmarkOut:
    """Alta de un benchmark (US-166)."""
    norm = normalize_movement_name(data.name)
    existente = await _id_by_norm(session, norm, exclude=None)
    if existente is not None:
        raise BenchmarkExists(existente)
    bench = Benchmark(
        name=clean_movement_name(data.name),
        name_norm=norm,
        description=data.description,
        score_type=data.score_type,
        created_by=by,
    )
    await _guardar_unico(session, norm, None, lambda: session.add(bench))
    logger.info("wods: benchmark creado", extra={"benchmark_id": str(bench.id)})
    return (await _outs(session, [bench]))[0]


async def _locked(session: AsyncSession, benchmark_id: UUID) -> Benchmark:
    bench = await session.scalar(
        select(Benchmark)
        .where(Benchmark.id == benchmark_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if bench is None:
        raise BenchmarkNotFound()
    return bench


async def update_benchmark(
    session: AsyncSession, benchmark_id: UUID, patch: BenchmarkPatch, by: UUID
) -> BenchmarkOut:
    """`PATCH` de un benchmark: solo lo enviado; ningún campo admite `null`."""
    bench = await _locked(session, benchmark_id)
    valores: dict[str, Any] = {}
    for campo in patch.model_fields_set & set(_EDITABLES):
        valor = getattr(patch, campo)
        if valor is None:
            raise WodsValidationError(message=_MENSAJE_NULO, field=campo)
        valores[campo] = clean_movement_name(valor) if campo == "name" else valor
    cambios = {c: v for c, v in valores.items() if getattr(bench, c) != v}
    if "score_type" in cambios and (await wod_counts(session, [bench.id])).get(bench.id, 0) > 0:
        raise ScoreTypeLocked()
    if not cambios:
        return (await _outs(session, [bench]))[0]
    norm = bench.name_norm
    if "name" in cambios:
        norm = normalize_movement_name(cambios["name"])
        otro = await _id_by_norm(session, norm, exclude=bench.id)
        if otro is not None:
            raise BenchmarkExists(otro)

    def aplicar() -> None:
        if "name" in cambios:
            bench.name_norm = norm
        for campo, valor in cambios.items():
            setattr(bench, campo, valor)

    await _guardar_unico(session, norm, bench.id, aplicar)
    logger.info(
        "wods: benchmark editado",
        extra={"benchmark_id": str(bench.id), "changed_fields": sorted(cambios), "actor": str(by)},
    )
    return (await _outs(session, [bench]))[0]


async def get_benchmark(session: AsyncSession, benchmark_id: UUID) -> BenchmarkOut:
    bench = await session.get(Benchmark, benchmark_id)
    if bench is None:
        raise BenchmarkNotFound()
    return (await _outs(session, [bench]))[0]


async def list_benchmarks(
    session: AsyncSession, filters: BenchmarkListQuery, page: PageParams, *, q: str | None = None
) -> Page[BenchmarkOut]:
    """`GET /benchmarks`: `q` (nombre, sin tildes ni mayúsculas) y `score_type`."""
    consulta = select(Benchmark)
    termino = clean_query(q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(sql_fold(Benchmark.name).ilike(patron, escape=LIKE_ESCAPE))
    if filters.score_type is not None:
        consulta = consulta.where(Benchmark.score_type == filters.score_type)
    benchs, total = await paginate(
        session, consulta.order_by(Benchmark.name_norm, Benchmark.id), page
    )
    return to_page(await _outs(session, benchs), total, page)
