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
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.alerts import alert
from app.core.db import DatabaseBusy, is_connection_error, translate_busy, violated_constraint
from app.core.events import EventDepthExceeded
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.records import current_benchmark, current_rm
from app.modules.athletes.rules import RecordDraft, derive_benchmark, derive_rm
from app.modules.results import service as results_service
from app.modules.results.schemas import ResultMark
from app.modules.results.service import WodResultValidated
from app.modules.wods import service as wods_service
from app.modules.wods.service import WodRecordMeta

logger = logging.getLogger("app.athletes")

UQ_RESULT_KIND: Final = "uq_personal_records_result_kind"


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


def _skip(event: WodResultValidated, error: Exception) -> None:
    """Fallo blando (S9-D30): ids solo en el log; la alerta, sin ids y en su propio `try`."""
    logger.warning(
        "athletes: derivación omitida",
        extra={
            "result_id": str(event.result_id),
            "member_id": str(event.member_id),
            "error_type": type(error).__name__,
        },
    )
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


def _possible(event: WodResultValidated, plan: _Plan, kind: str) -> bool:
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


async def _insert(draft: RecordDraft, plan: _Plan, session: AsyncSession) -> None:
    mark = plan.mark
    record = _record_of(draft, mark.member_id, plan.by)
    session.add(record)
    await session.flush()
    await events.emit(
        PersonalRecordSet(
            record_id=record.id,
            member_id=mark.member_id,
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
        await _insert(draft, plan, session)


async def _derive_benchmark(plan: _Plan, session: AsyncSession) -> None:
    mark, meta = plan.mark, plan.meta
    if meta.benchmark_id is None:  # lo garantiza derive_benchmark; el tipo lo exige
        return
    current = await current_benchmark(session, mark.member_id, meta.benchmark_id, meta.score_type)
    draft = derive_benchmark(mark, meta, current)
    if draft is not None:
        await _insert(draft, plan, session)


async def _guarded[T](
    event: WodResultValidated, session: AsyncSession, work: Callable[[], Awaitable[T]]
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


def subscribe_handlers() -> None:
    """Suscribe los handlers al bus; `athletes/service.py` lo llama al importarse (S9-D7)."""
    events.subscribe(WodResultValidated, on_wod_result_validated)
