"""Handlers de `athletes` sobre los eventos de `results` (S9-B3 y S9-B4, US-181 y US-182; S9-D7,
S9-D10, S9-D30, S9-D42, S9-D57 a S9-D59). Privado del módulo.

- `on_wod_result_validated(event, session)`: `flush` FUERA y TRES tramos, cada uno en SU
  `begin_nested()` (S9-D58): (1) preludio `_plan`: `results.service.get_mark` (si no es
  `validated` y vigente, sale) y `wods.service.record_meta_for`; (2) `_derive_rm`: lee el RM
  vigente (`current_rm`) y, si `derive_rm` da borrador, inserta UN récord `derived`; (3)
  `_derive_benchmark`: lee el vigente del benchmark (`current_benchmark`, por `score_key`) y
  aplica `derive_benchmark`. Un WOD `load` con principal y benchmark deriva los DOS. Cada regla
  se evalúa con vigente `None` en su propio `try` (`_possible`): una regla que lanza no omite al
  otro récord, y un tramo sin récord posible no abre savepoint ni lee el vigente (S9-D30).
  `created_by = mark.validated_by`. Sin candados propios: el emisor (`results`) ya tiene el
  candado del socio (S9-D7). Un récord derivado se inserta sin lectura con candado del catálogo
  porque exige un WOD que use el movimiento (S9-D56).
- Clasificación de errores de `_guarded` (S9-D42, S9-D57, S9-D59): un 23505 de
  `uq_personal_records_result_kind` es no-op sin alerta; se RE-LANZAN `DatabaseBusy`,
  `EventDepthExceeded`, un `DBAPIError` «ocupado» (`translate_busy`, 503 `busy`) y un fallo de
  CONEXIÓN (`is_connection_error`: no se siguen los tramos restantes); cualquier otra
  `Exception` es fallo blando (S9-D30): log `derivación omitida` con los ids y
  `alert("athletes_derive_skipped", error_type=...)` en su propio `try`, sin ids.
- S9-B5 (US-181; S9-D10, S9-D11, S9-D30, S9-D42): `on_wod_result_superseded` y
  `on_wod_result_voided` INVALIDAN con `_invalidate` (por ORM, `flush` fuera de todo savepoint:
  falla CERRADO, un RM falso vigente no lo repara ningún comando) y REPONEN con `_restore_best`
  (dentro de su savepoint, con la clasificación de `_guarded`: fallo blando, «ocupado» = 503).
  `on_wod_result_validated` repone al final cuando la marca corrige a otra (`supersedes_id`).
  `restore_after_manual` es la puerta de la reposición tras invalidar un récord manual.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.alerts import alert
from app.core.context import get_actor
from app.core.db import DatabaseBusy, is_connection_error, translate_busy, violated_constraint
from app.core.events import EventDepthExceeded
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.records import (
    current_benchmark,
    current_rm,
    result_ids_with_record,
)
from app.modules.athletes.rules import (
    RecordDraft,
    best_candidate,
    derive_benchmark,
    derive_rm,
)
from app.modules.results import service as results_service
from app.modules.results.schemas import ResultMark
from app.modules.results.service import WodResultSuperseded, WodResultValidated, WodResultVoided
from app.modules.wods import service as wods_service
from app.modules.wods.service import WodRecordMeta

logger = logging.getLogger("app.athletes")

UQ_RESULT_KIND: Final = "uq_personal_records_result_kind"
RESTORE_MAX_MARKS: Final = 200  # S9-D30: tope de marcas candidatas de la reposición


def _record_of(draft: RecordDraft, member_id: UUID, by: UUID) -> PersonalRecord:
    return PersonalRecord(
        created_by=by,
        member_id=member_id,
        kind=draft.kind,
        movement_id=draft.movement_id,
        benchmark_id=draft.benchmark_id,
        value_g=draft.value_g,
        level=draft.level,
        seconds=draft.seconds,
        rounds=draft.rounds,
        reps=draft.reps,
        load_g=draft.load_g,
        capped=draft.capped,
        achieved_on=draft.achieved_on,
        source="derived",
        result_id=draft.result_id,
        wod_id=draft.wod_id,
    )


@dataclass(frozen=True, slots=True)
class _ManualSource:
    """Quién origina una reposición sin evento (la invalidación de un récord manual): solo el socio
    para el log; no hay resultado."""

    member_id: UUID
    result_id: UUID | None = None


_Source = WodResultValidated | WodResultVoided | _ManualSource


def _skip(event: _Source, error: Exception) -> None:
    """Fallo blando (S9-D30): ids solo en el log; la alerta, sin ids y en su propio `try`."""
    datos = {"member_id": str(event.member_id), "error_type": type(error).__name__}
    if event.result_id is None:  # la reposición tras invalidar un manual: no hay resultado
        logger.warning("athletes: reposición omitida", extra=datos)
    else:
        datos["result_id"] = str(event.result_id)
        logger.warning("athletes: derivación omitida", extra=datos)
    try:
        alert("athletes_derive_skipped", error_type=type(error).__name__)
    except Exception as alert_error:
        logger.warning("athletes: alerta omitida", extra={"error_type": type(alert_error).__name__})


@dataclass(frozen=True, slots=True)
class _Plan:
    """Lo que el preludio leyó: la marca, el WOD y quién validó (el actor de los récords)."""

    mark: ResultMark
    meta: WodRecordMeta
    by: UUID


async def _plan(event: WodResultValidated, session: AsyncSession) -> _Plan | None:
    """Preludio (lecturas, DENTRO de su savepoint): la marca vigente validada y el WOD."""
    mark = await results_service.get_mark(session, event.result_id)
    if mark is None or mark.status != "validated" or not mark.is_current:
        return None
    if mark.validated_by is None:  # un validado siempre lo trae (CHECK `validated_pair`)
        logger.warning(
            "athletes: resultado validado sin validador",
            extra={"result_id": str(event.result_id), "member_id": str(event.member_id)},
        )
        return None
    meta = (await wods_service.record_meta_for(session, [mark.wod_id])).get(mark.wod_id)
    if meta is None:
        return None
    return _Plan(mark, meta, mark.validated_by)


def _possible(event: _Source, plan: _Plan, kind: str) -> bool:
    """¿Puede nacer un récord de ese `kind`? Regla pura con vigente `None` (la más permisiva), en su
    propio `try`: si ni así deriva no se lee el vigente ni se abre savepoint (S9-D30); si lanza es
    fallo blando de ESE récord y el otro sigue (S9-D59, LOW-2)."""
    mark, meta = plan.mark, plan.meta
    try:
        if kind == "rm":
            return derive_rm(mark, meta, None) is not None
        if meta.benchmark_id is not None and mark.benchmark_id != meta.benchmark_id:
            logger.warning(
                "athletes: la marca no es del benchmark del WOD",
                extra={
                    "result_id": str(mark.result_id),
                    "member_id": str(mark.member_id),
                    "wod_id": str(mark.wod_id),
                },
            )
            return False
        return derive_benchmark(mark, meta, None) is not None
    except Exception as error:
        if is_connection_error(error):
            raise
        _skip(event, error)
        return False


async def _insert(draft: RecordDraft, member_id: UUID, by: UUID, session: AsyncSession) -> None:
    record = _record_of(draft, member_id, by)
    session.add(record)
    await session.flush()
    await events.emit(
        PersonalRecordSet(
            record_id=record.id,
            member_id=member_id,
            kind="rm" if draft.kind == "rm" else "benchmark",
            movement_id=draft.movement_id,
            benchmark_id=draft.benchmark_id,
            source="derived",
            achieved_on=draft.achieved_on,
        ),
        session,
    )


async def _derive_rm(plan: _Plan, session: AsyncSession) -> None:
    mark, meta = plan.mark, plan.meta
    if meta.primary_movement_id is None:  # lo garantiza derive_rm; el tipo lo exige
        return
    current = await current_rm(session, mark.member_id, meta.primary_movement_id)
    draft = derive_rm(mark, meta, current)
    if draft is not None:
        await _insert(draft, mark.member_id, plan.by, session)


async def _derive_benchmark(plan: _Plan, session: AsyncSession) -> None:
    mark, meta = plan.mark, plan.meta
    if meta.benchmark_id is None:  # lo garantiza derive_benchmark; el tipo lo exige
        return
    current = await current_benchmark(session, mark.member_id, meta.benchmark_id, meta.score_type)
    draft = derive_benchmark(mark, meta, current)
    if draft is not None:
        await _insert(draft, mark.member_id, plan.by, session)


async def _guarded[T](
    event: _Source, session: AsyncSession, work: Callable[[], Awaitable[T]]
) -> T | None:
    """Corre `work` en SU savepoint (S9-D57, S9-D58): lo que sale de aquí es el valor o `None`
    si fue un no-op o un fallo blando. Se re-lanzan `DatabaseBusy`, `EventDepthExceeded` y todo
    `DBAPIError` «ocupado»; un 23505 de `uq_personal_records_result_kind` es no-op sin alerta."""
    try:
        async with session.begin_nested():
            return await work()
    except (DatabaseBusy, EventDepthExceeded):
        raise
    except DBAPIError as error:
        if translate_busy(error) is not None or is_connection_error(error):
            raise
        if isinstance(error, IntegrityError) and violated_constraint(error) == UQ_RESULT_KIND:
            return None  # el evento llegó dos veces: no-op, sin alerta (US-181 CA6)
        _skip(event, error)
    except Exception as error:
        if is_connection_error(error):  # un `OSError` de conexión pelado no es un `DBAPIError`
            raise
        _skip(event, error)
    return None


async def on_wod_result_validated(event: WodResultValidated, session: AsyncSession) -> None:
    """Deriva los récords del resultado recién validado (S9-D10). Un savepoint por cada tramo
    (preludio, RM, benchmark; S9-D58, S9-D59): todo el trabajo de un récord va dentro del suyo, y
    un fallo blando en uno no deshace los demás ni el resultado."""
    await session.flush()  # lo pendiente del emisor falla cerrado, FUERA de los savepoints
    plan = await _guarded(event, session, lambda: _plan(event, session))
    if plan is None:
        return
    if _possible(event, plan, "rm"):
        await _guarded(event, session, lambda: _derive_rm(plan, session))
    if _possible(event, plan, "benchmark"):
        await _guarded(event, session, lambda: _derive_benchmark(plan, session))
    if plan.mark.supersedes_id is not None:  # S9-D10: la marca corrige a otra
        await _restore_superseded(event, session, plan.mark)


# S9-B5 (US-181; S9-D7, S9-D10, S9-D11, S9-D30, S9-D42): invalidar y reponer -----------------------


@dataclass(frozen=True, slots=True)
class _Target:
    """El objetivo de un récord invalidado: un movimiento (`rm`) o un benchmark."""

    kind: Literal["rm", "benchmark"]
    target_id: UUID


def _target_of(kind: str, movement_id: UUID | None, benchmark_id: UUID | None) -> _Target | None:
    if kind == "rm" and movement_id is not None:
        return _Target("rm", movement_id)
    if kind == "benchmark" and benchmark_id is not None:
        return _Target("benchmark", benchmark_id)
    return None  # la forma de la tabla (CHECK) lo impide


async def _invalidate(
    session: AsyncSession,
    *,
    member_id: UUID,
    result_id: UUID,
    reason: Literal["superseded", "voided"],
    by_result: UUID | None,
) -> list[_Target]:
    """Invalida por ORM (S9-D42) los récords `derived` VIVOS de ese resultado: lee las filas
    (`uq_personal_records_result_kind`), asigna `invalidated_at` y `updated_at` con el
    `clock_timestamp()` de la base (S9-D52: el reloj de la aplicación puede ir detrás del
    `created_at`), `invalidated_reason`, `invalidated_by` (actor del contexto) e
    `invalidated_by_result_id` (solo `superseded`) y hace `flush` FUERA de todo savepoint: falla
    CERRADO (S9-D30). Cada fila deja su `update` en `audit_log`. Devuelve los objetivos tocados
    (su cuenta es cuántas tocó; el de una anulación los necesita para reponer). Sin candados
    propios: el emisor ya tiene `lock_member`."""
    filas = (
        await session.scalars(
            select(PersonalRecord)
            .where(
                PersonalRecord.member_id == member_id,
                PersonalRecord.result_id == result_id,
                PersonalRecord.source == "derived",
                PersonalRecord.invalidated_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    if not filas:
        return []
    ahora = (await session.execute(select(func.clock_timestamp()))).scalar_one()
    actor = get_actor()
    for fila in filas:
        fila.invalidated_at = ahora
        fila.updated_at = ahora
        fila.invalidated_reason = reason
        fila.invalidated_by = actor
        fila.invalidated_by_result_id = by_result
    await session.flush()
    tocados = (_target_of(f.kind, f.movement_id, f.benchmark_id) for f in filas)
    return [t for t in tocados if t is not None]


def _draft_from_mark(mark: ResultMark, target: _Target) -> RecordDraft:
    """El borrador del récord que repone `mark` (ya elegida por `best_candidate`)."""
    es_rm = target.kind == "rm"
    return RecordDraft(
        kind=target.kind,
        movement_id=target.target_id if es_rm else None,
        benchmark_id=None if es_rm else target.target_id,
        value_g=mark.load_g if es_rm else None,
        level=None if es_rm else mark.level,
        seconds=None if es_rm else mark.seconds,
        rounds=None if es_rm else mark.rounds,
        reps=None if es_rm else mark.reps,
        load_g=None if es_rm else mark.load_g,
        capped=False if es_rm else mark.capped,
        achieved_on=mark.wod_date,
        result_id=mark.result_id,
        wod_id=mark.wod_id,
    )


def _alert_capped(marcas: int) -> None:
    """Tope de marcas candidatas alcanzado (S9-D30): alerta con el conteo, sin ids y en su `try`."""
    try:
        alert("athletes_restore_capped", marcas=marcas)
    except Exception as error:
        logger.warning("athletes: alerta omitida", extra={"error_type": type(error).__name__})


async def _candidate_marks(
    session: AsyncSession, member_id: UUID, target: _Target
) -> tuple[list[ResultMark], str | None]:
    """Las marcas vigentes y validadas del objetivo, filtradas EN SQL y con tope (S9-D11, S9-D30):
    RM por los WODs `load` con ese principal; benchmark por `benchmark_id`. Devuelve también el
    tipo de marca del benchmark (`None` en un RM)."""
    limite = RESTORE_MAX_MARKS + 1
    if target.kind == "rm":
        wod_ids = await wods_service.wod_ids_with_primary(session, target.target_id)
        if not wod_ids:
            return [], None
        marcas = await results_service.member_marks(
            session, member_id, wod_ids=wod_ids, only_load=True, limit=limite
        )
        return marcas, None
    ref = (await wods_service.benchmark_refs(session, [target.target_id])).get(target.target_id)
    if ref is None:
        return [], None
    marcas = await results_service.member_marks(
        session, member_id, benchmark_id=target.target_id, limit=limite
    )
    return marcas, ref.score_type


async def _restore(session: AsyncSession, member_id: UUID, target: _Target) -> None:
    """Repone UN récord derivado con la mejor marca SIN récord, si supera al vigente (S9-D11)."""
    marcas, score_type = await _candidate_marks(session, member_id, target)
    if len(marcas) > RESTORE_MAX_MARKS:
        _alert_capped(len(marcas))
        return
    con_record = await result_ids_with_record(
        session, member_id, target.kind, [m.result_id for m in marcas]
    )
    candidatas = [m for m in marcas if m.result_id not in con_record]
    if not candidatas:
        return
    if target.kind == "rm":
        vigente = await current_rm(session, member_id, target.target_id)
    else:
        vigente = await current_benchmark(session, member_id, target.target_id, score_type or "")
    mejor = best_candidate(candidatas, kind=target.kind, score_type=score_type, current=vigente)
    if mejor is not None:
        await _insert(_draft_from_mark(mejor, target), member_id, get_actor(), session)


async def _restore_best(
    event: _Source,
    session: AsyncSession,
    *,
    member_id: UUID,
    kind: Literal["rm", "benchmark"],
    target_id: UUID,
) -> None:
    """Repone UN récord derivado con la mejor marca sin récord vivo (S9-D11), DENTRO de su
    savepoint y con la clasificación de `_guarded` (fallo blando; «base ocupada» sale 503). Pide
    `member_marks` con filtro en SQL (RM: `wods.wod_ids_with_primary`; benchmark: `benchmark_id`)
    y a lo sumo `RESTORE_MAX_MARKS + 1` marcas: si hay más de `RESTORE_MAX_MARKS`, alerta
    `athletes_restore_capped` con `marcas=N` (sin ids) y NO repone."""
    target = _Target(kind, target_id)
    await _guarded(event, session, lambda: _restore(session, member_id, target))


async def _superseded_targets(session: AsyncSession, mark: ResultMark) -> list[_Target]:
    """Los objetivos de los récords que la corrección `mark` invalidó (S9-D30): las filas del
    resultado anterior con `invalidated_by_result_id` = el nuevo (UNA lectura por
    `uq_personal_records_result_kind`)."""
    if mark.supersedes_id is None:
        return []
    filas = await session.execute(
        select(PersonalRecord.kind, PersonalRecord.movement_id, PersonalRecord.benchmark_id).where(
            PersonalRecord.result_id == mark.supersedes_id,
            PersonalRecord.member_id == mark.member_id,
            PersonalRecord.invalidated_by_result_id == mark.result_id,
        )
    )
    tocados = (_target_of(f.kind, f.movement_id, f.benchmark_id) for f in filas)
    return [t for t in tocados if t is not None]


async def _restore_superseded(
    event: WodResultValidated, session: AsyncSession, mark: ResultMark
) -> None:
    """Tras derivar la marca corregida, repone por cada objetivo cuyo récord invalidó la
    corrección (S9-D10, S9-D11). Sin récord invalidado no se lee ninguna marca."""
    objetivos = await _guarded(event, session, lambda: _superseded_targets(session, mark))
    for objetivo in objetivos or []:
        await _restore_best(
            event,
            session,
            member_id=mark.member_id,
            kind=objetivo.kind,
            target_id=objetivo.target_id,
        )


async def restore_after_manual(
    session: AsyncSession, member_id: UUID, *, kind: Literal["rm", "benchmark"], target_id: UUID
) -> None:
    """Reposición tras invalidar un récord MANUAL (S9-D13): la misma regla y el mismo fallo
    blando que la de un resultado; sin evento, el log lleva solo el socio."""
    await _restore_best(
        _ManualSource(member_id), session, member_id=member_id, kind=kind, target_id=target_id
    )


async def on_wod_result_superseded(event: WodResultSuperseded, session: AsyncSession) -> None:
    """`WodResultSuperseded`: `_invalidate(result_id=old_result_id, reason="superseded",
    by_result=new_result_id)` (que hace `flush`); falla cerrado. No repone: lo hace
    `on_wod_result_validated` del nuevo al final, cuando tiene `supersedes_id` (S9-D10, S9-D11)."""
    await _invalidate(
        session,
        member_id=event.member_id,
        result_id=event.old_result_id,
        reason="superseded",
        by_result=event.new_result_id,
    )


async def on_wod_result_voided(event: WodResultVoided, session: AsyncSession) -> None:
    """`WodResultVoided`: `_invalidate(reason="voided")` (falla cerrado) y, solo si tocó filas,
    `_restore_best` del `kind` y el objetivo de cada fila tocada (S9-D30)."""
    tocados = await _invalidate(
        session,
        member_id=event.member_id,
        result_id=event.result_id,
        reason="voided",
        by_result=None,
    )
    for objetivo in tocados:
        await _restore_best(
            event,
            session,
            member_id=event.member_id,
            kind=objetivo.kind,
            target_id=objetivo.target_id,
        )


def subscribe_handlers() -> None:
    """Suscribe los handlers al bus; `athletes/service.py` lo llama al importarse (S9-D7)."""
    events.subscribe(WodResultValidated, on_wod_result_validated)
    events.subscribe(WodResultSuperseded, on_wod_result_superseded)
    events.subscribe(WodResultVoided, on_wod_result_voided)
