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
from collections.abc import Sequence
from datetime import date
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Select, func, select, union_all
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alerts import alert
from app.core.pagination import Page, PageParams, to_page
from app.core.search import clean_query, strip_accents
from app.modules.athletes.models import BodyMetric, PersonalRecord
from app.modules.athletes.records import KIND_SQL
from app.modules.athletes.rules import (
    Attempt,
    BenchmarkSummary,
    RecordRow,
    summarize_benchmarks,
    summarize_records,
)
from app.modules.athletes.rules import benchmark_series as _series
from app.modules.athletes.schemas import (
    AthleteSummaryOut,
    AttemptOut,
    BenchmarkRowOut,
    BenchmarkSeriesOut,
    RmOut,
    ScoreOut,
    SummaryRecordOut,
)
from app.modules.members import service as members_service
from app.modules.results import service as results_service
from app.modules.results.schemas import ResultMark
from app.modules.wods import service as wods_service
from app.modules.wods.exceptions import BenchmarkNotFound
from app.modules.wods.service import BenchmarkRef, MovementRef

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


# S9-C2 (US-184, S9-D27): RMs vigentes y resumen --------------------------------------------------

LIVE_RECORDS_MAX: Final = 2_000  # tope de récords vivos que lee el resumen


# Columnas del resumen (L-3): sin entidades ORM completas.
_SUMMARY_COLUMNS: Final = (
    PersonalRecord.id,
    PersonalRecord.kind,
    PersonalRecord.movement_id,
    PersonalRecord.benchmark_id,
    PersonalRecord.value_g,
    PersonalRecord.level,
    PersonalRecord.seconds,
    PersonalRecord.rounds,
    PersonalRecord.reps,
    PersonalRecord.load_g,
    PersonalRecord.capped,
    PersonalRecord.achieved_on,
    PersonalRecord.created_at,
    PersonalRecord.source,
    PersonalRecord.wod_id,
)


def current_rms_query(member_id: UUID, *columns: Any) -> Select[Any]:
    """Un RM vigente por movimiento: `DISTINCT ON (movement_id)` con el orden de `pick_current`
    (mayor `value_g`, `achieved_on`, `created_at` e id más antiguos). `kind` literal y
    `invalidated_at IS NULL` con la columna desnuda: el predicado de `ix_personal_records_rm`
    (S8-D50, S9-D55). Sin `columns` trae la entidad; con ellas, solo esas columnas."""
    return (
        select(*(columns or (PersonalRecord,)))
        .where(
            PersonalRecord.member_id == member_id,
            PersonalRecord.kind == KIND_SQL["rm"],
            PersonalRecord.invalidated_at.is_(None),
        )
        .ext(distinct_on(PersonalRecord.movement_id))
        .order_by(
            PersonalRecord.movement_id,
            PersonalRecord.value_g.desc(),
            PersonalRecord.achieved_on,
            PersonalRecord.created_at,
            PersonalRecord.id,
        )
    )


def _drop_rms_without_value(filas: Sequence[Any]) -> list[Any]:
    """L-5: un RM sin movimiento o sin valor no se muestra como 0 g: se omite y se avisa (el CHECK
    `rm_shape` lo impide; esto es defensa)."""
    buenas = [f for f in filas if f.movement_id is not None and f.value_g is not None]
    if len(buenas) != len(filas):
        logger.warning(
            "athletes: RM sin valor omitido", extra={"omitidos": len(filas) - len(buenas)}
        )
    return buenas


async def list_rms(
    session: AsyncSession, member_id: UUID, page: PageParams, *, q: str | None = None
) -> Page[RmOut]:
    """RMs vigentes del socio, un ítem por movimiento, por nombre (los sin nombre, al final).

    Una fila por movimiento sale de SQL; los nombres, por lote del catálogo; `q` filtra por el
    nombre (sin tildes ni mayúsculas, texto literal) ANTES de paginar y el `total` lo refleja. No
    descifra nada; el socio dado de baja también se lee."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    filas = _drop_rms_without_value((await session.scalars(current_rms_query(member_id))).all())
    refs = await wods_service.movement_refs(session, {f.movement_id for f in filas})
    items: list[tuple[str | None, RmOut]] = []
    for f in filas:
        nombre = refs[f.movement_id].name if f.movement_id in refs else None
        items.append(
            (
                nombre,
                RmOut(
                    movement_id=f.movement_id,
                    movement_name=nombre,
                    record_id=f.id,
                    value_g=f.value_g,
                    source=f.source,
                    achieved_on=f.achieved_on,
                ),
            )
        )
    items.sort(key=lambda par: (par[0] is None, (par[0] or "").casefold(), par[1].movement_id))
    termino = strip_accents(clean_query(q))
    if termino:
        items = [p for p in items if p[0] is not None and termino in strip_accents(p[0])]
    salida = [p[1] for p in items]
    return to_page(salida[page.offset : page.offset + page.limit], len(salida), page)


async def _metrics_digest(session: AsyncSession, member_id: UUID) -> tuple[date | None, int]:
    """Última fecha y número de mediciones VIGENTES (no anuladas), en una consulta agregada."""
    fila = (
        await session.execute(
            select(func.max(BodyMetric.measured_on), func.count()).where(
                BodyMetric.member_id == member_id, BodyMetric.voided_at.is_(None)
            )
        )
    ).one()
    return fila[0], int(fila[1])


def _warn_summary_capped(member_id: UUID, filas: int, origen: str) -> None:
    """Tope de lectura del resumen (S9-D64): log con el socio (solo log) y alerta propia con el
    conteo, sin ids; la respuesta sigue con `truncated`."""
    logger.warning(
        "athletes: resumen al tope de lectura",
        extra={"member_id": str(member_id), "origen": origen, "filas": filas},
    )
    try:
        alert("athletes_summary_capped", marcas=filas)
    except Exception as error:
        logger.warning("athletes: alerta omitida", extra={"error_type": type(error).__name__})


async def _records_rows(session: AsyncSession, member_id: UUID) -> list[Any]:
    """UNA consulta: un RM vigente por movimiento (SQL, sin tope) y los récords de benchmark vivos
    (en memoria, con tope `LIVE_RECORDS_MAX`), solo con las columnas que el resumen usa."""
    rm = current_rms_query(member_id, *_SUMMARY_COLUMNS).subquery("rm")
    benchmarks = (
        select(*_SUMMARY_COLUMNS)
        .where(
            PersonalRecord.member_id == member_id,
            PersonalRecord.kind == KIND_SQL["benchmark"],
            PersonalRecord.invalidated_at.is_(None),
        )
        .order_by(
            PersonalRecord.achieved_on.desc(),
            PersonalRecord.created_at.desc(),
            PersonalRecord.id.desc(),
        )
        .limit(LIVE_RECORDS_MAX)
        .subquery("bm")
    )
    return list((await session.execute(union_all(select(rm), select(benchmarks)))).all())


def _record_row(f: Any) -> RecordRow:
    return RecordRow(
        id=f.id,
        kind=f.kind,
        movement_id=f.movement_id,
        benchmark_id=f.benchmark_id,
        value_g=f.value_g,
        level=f.level,
        seconds=f.seconds,
        rounds=f.rounds,
        reps=f.reps,
        load_g=f.load_g,
        capped=f.capped,
        achieved_on=f.achieved_on,
        created_at=f.created_at,
        source=f.source,
    )


def _summary_record(
    r: RecordRow, wod_id: UUID | None, mov: MovementRef | None, bm: BenchmarkRef | None
) -> SummaryRecordOut:
    return SummaryRecordOut(
        id=r.id,
        kind=r.kind,
        movement_id=r.movement_id,
        movement_name=mov.name if mov else None,
        benchmark_id=r.benchmark_id,
        benchmark_name=bm.name if bm else None,
        score_type=bm.score_type if bm else None,
        value_g=r.value_g,
        level=r.level,
        seconds=r.seconds,
        rounds=r.rounds,
        reps=r.reps,
        load_g=r.load_g,
        capped=r.capped,
        achieved_on=r.achieved_on,
        source=r.source,
        wod_id=wod_id,
    )


async def _split_records(
    session: AsyncSession, member_id: UUID
) -> tuple[list[Any], list[Any], bool]:
    """RM vigentes y benchmarks vivos; con el tope alcanzado, avisa y devuelve ningún benchmark."""
    filas = await _records_rows(session, member_id)
    rms = _drop_rms_without_value([f for f in filas if f.kind == "rm"])
    vivos_bm = [f for f in filas if f.kind == "benchmark"]
    if len(vivos_bm) < LIVE_RECORDS_MAX:
        return rms, vivos_bm, False
    _warn_summary_capped(member_id, len(vivos_bm), "records")
    return rms, [], True


async def summary(session: AsyncSession, member_id: UUID) -> AthleteSummaryOut:
    """El resumen del atleta (US-184 CA1): sin descifrar nada y con a lo sumo seis consultas
    (socio, medidas, marcas, récords, catálogo de benchmarks y de movimientos; S9-D16). Los RM
    salen de SQL sin tope; con un tope alcanzado: `truncated` y sin benchmarks (S9-D64)."""
    await members_service.ensure_exists(session, member_id, include_deleted=True)
    ultima, cuantas = await _metrics_digest(session, member_id)
    marcas = await results_service.member_marks(
        session, member_id, only_benchmarks=True, limit=MEMBER_MARKS_MAX
    )
    truncado = len(marcas) >= MEMBER_MARKS_MAX
    if truncado:
        _warn_summary_capped(member_id, len(marcas), "marcas")
    rms, vivos_bm, cortado = await _split_records(session, member_id)
    truncado = truncado or cortado
    benchmarks = await wods_service.benchmark_refs(
        session, {f.benchmark_id for f in vivos_bm if f.benchmark_id}
    )
    digest = summarize_records(
        [_record_row(f) for f in (*rms, *vivos_bm)],
        {b.id: b.score_type for b in benchmarks.values()},
    )
    por_id = {f.id: f for f in (*rms, *vivos_bm)}
    movimientos = await wods_service.movement_refs(
        session, {r.movement_id for r in digest.recent if r.movement_id}
    )
    salida = [
        _summary_record(
            r,
            por_id[r.id].wod_id,
            movimientos.get(r.movement_id) if r.movement_id else None,
            benchmarks.get(r.benchmark_id) if r.benchmark_id else None,
        )
        for r in digest.recent
    ]
    return AthleteSummaryOut(
        last_metric_on=ultima,
        metrics_count=cuantas,
        current_rms=len(rms),
        benchmarks_with_attempts=len({m.benchmark_id for m in marcas if m.benchmark_id}),
        recent_records=salida,
        truncated=truncado,
    )
