"""Lecturas de benchmarks del socio (S9-C1, US-183; S9-D6, S9-D27, S9-D55).

- `list_benchmarks`: benchmarks con al menos un intento VIGENTE y VALIDADO (fuera `pending`,
  corregidos y anulados), por nombre, paginados en memoria sobre
  `results.service.member_marks(only_benchmarks=True)` (una consulta por
  `ix_wod_results_member_date`, tope `MEMBER_MARKS_MAX`) y nombres del catálogo por lote.
- `benchmark_series`: la serie de UN benchmark por `results.service.member_marks(benchmark_id=...,
  limit=SERIES_MAX)`; 404 `benchmark_not_found` si el id no está en el catálogo; sin intentos,
  lista vacía con 200.
Solo lectura, sin candados y sin descifrar nada: la respuesta no trae campos cifrados. El socio
dado de baja también se lee, como en las demás lecturas de `athletes`.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alerts import alert
from app.core.pagination import Page, PageParams, to_page
from app.core.search import clean_query, strip_accents
from app.modules.athletes.rules import Attempt, BenchmarkSummary, summarize_benchmarks
from app.modules.athletes.rules import benchmark_series as _series
from app.modules.athletes.schemas import (
    AttemptOut,
    BenchmarkRowOut,
    BenchmarkSeriesOut,
    ScoreOut,
)
from app.modules.members import service as members_service
from app.modules.results import service as results_service
from app.modules.results.schemas import ResultMark
from app.modules.wods import service as wods_service
from app.modules.wods.exceptions import BenchmarkNotFound

logger = logging.getLogger("app.athletes")

SERIES_MAX: Final = 200  # S9-D27: a lo sumo 200 intentos por serie (los más recientes)
MEMBER_MARKS_MAX: Final = results_service.MEMBER_MARKS_MAX  # tope de marcas de la lista (S9-D63)


def _score(mark: ResultMark) -> ScoreOut:
    return ScoreOut(
        level=mark.level,
        seconds=mark.seconds,
        rounds=mark.rounds,
        reps=mark.reps,
        load_g=mark.load_g,
        capped=mark.capped,
    )


def _attempt(intento: Attempt) -> AttemptOut:
    m = intento.mark
    return AttemptOut(
        **_score(m).model_dump(),
        result_id=m.result_id,
        wod_id=m.wod_id,
        wod_date=m.wod_date,
        source=m.source,
        is_best=intento.is_best,
        level_changed=intento.level_changed,
    )


def _row(resumen: BenchmarkSummary, name: str, score_type: str) -> BenchmarkRowOut:
    return BenchmarkRowOut(
        benchmark_id=resumen.benchmark_id,
        name=name,
        score_type=score_type,
        attempts=resumen.attempts,
        best=_score(resumen.best),
        last_on=resumen.last_on,
    )


def _warn_capped(member_id: UUID, marcas: int) -> None:
    """Tope de marcas alcanzado (S9-D63): la lista puede omitir intentos viejos. Log con el socio
    (solo log) y alerta con el conteo, sin ids; la respuesta sigue."""
    logger.warning(
        "athletes: lista de benchmarks al tope de marcas",
        extra={"member_id": str(member_id), "marcas": marcas},
    )
    try:
        alert("athletes_restore_capped", marcas=marcas)
    except Exception as error:
        logger.warning("athletes: alerta omitida", extra={"error_type": type(error).__name__})


async def list_benchmarks(
    session: AsyncSession, member_id: UUID, page: PageParams, *, q: str | None = None
) -> Page[BenchmarkRowOut]:
    """Benchmarks con intentos vigentes y validados del socio, por nombre (y id).

    `q` filtra por el nombre del catálogo (sin tildes ni mayúsculas, texto literal) ANTES de
    paginar; el `total` refleja el filtro."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    marcas = await results_service.member_marks(
        session, member_id, only_benchmarks=True, limit=MEMBER_MARKS_MAX
    )
    if len(marcas) >= MEMBER_MARKS_MAX:
        _warn_capped(member_id, len(marcas))
    refs = await wods_service.benchmark_refs(
        session, {m.benchmark_id for m in marcas if m.benchmark_id}
    )
    huerfanas = sum(1 for m in marcas if m.benchmark_id not in refs)
    if huerfanas:
        logger.warning(
            "athletes: marcas de benchmarks fuera del catálogo", extra={"marcas": huerfanas}
        )
    resumenes = summarize_benchmarks(marcas, {bid: r.score_type for bid, r in refs.items()})
    filas = sorted(
        (_row(r, refs[r.benchmark_id].name, refs[r.benchmark_id].score_type) for r in resumenes),
        key=lambda f: (f.name.casefold(), f.benchmark_id),
    )
    termino = strip_accents(clean_query(q))
    if termino:
        filas = [f for f in filas if termino in strip_accents(f.name)]
    return to_page(filas[page.offset : page.offset + page.limit], len(filas), page)


async def benchmark_series(
    session: AsyncSession, member_id: UUID, benchmark_id: UUID
) -> BenchmarkSeriesOut:
    """La serie del socio en un benchmark del catálogo (máximo `SERIES_MAX`, ascendente).

    Pide `SERIES_MAX + 1` marcas para saber si hubo más: `truncated` es verdadero y entonces
    `is_best` es el mejor de los intentos MOSTRADOS (S9-D63)."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    ref = (await wods_service.benchmark_refs(session, {benchmark_id})).get(benchmark_id)
    if ref is None:
        raise BenchmarkNotFound()
    marcas = await results_service.member_marks(
        session, member_id, benchmark_id=benchmark_id, limit=SERIES_MAX + 1
    )
    truncada = len(marcas) > SERIES_MAX
    mostradas = marcas[-SERIES_MAX:] if truncada else marcas
    return BenchmarkSeriesOut(
        benchmark_id=ref.id,
        name=ref.name,
        score_type=ref.score_type,
        attempts=[_attempt(a) for a in _series(mostradas, ref.score_type)],
        truncated=truncada,
    )
