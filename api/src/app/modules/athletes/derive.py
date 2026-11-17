"""Handlers de `athletes` sobre los eventos de `results` (S9-B3, US-181; S9-D7, S9-D10, S9-D30,
S9-D42). Privado del módulo.

- `on_wod_result_validated(event, session)`: `results.service.get_mark`; si no es `validated` y
  vigente, sale; `wods.service.record_meta_for`; lee el RM vigente del socio; `derive_rm`; inserta
  UN récord `derived` con `created_by = mark.validated_by`. Sin candados propios: el emisor
  (`results`) ya tiene el candado del socio, que serializa todo lo que decide «el vigente»
  (S9-D7). Un récord derivado se inserta sin lectura con candado del catálogo porque exige un WOD
  que use el movimiento: la guarda de uso de `wods` y el puerto de récords impiden cambiar su
  unidad mientras exista (S9-D56, probado en `test_derive_rm_service.py`).
- Patrón del savepoint (S9-D42, el de `wods/benchmarks.py`): lo pendiente se vacía con `flush`
  FUERA; dentro de `session.begin_nested()` van `add`, `flush` y la emisión de
  `PersonalRecordSet`; el `except` queda fuera del bloque. Un 23505 de
  `uq_personal_records_result_kind` es un no-op sin alerta; un `DBAPIError` «ocupado»
  (`translate_busy`) se re-lanza tal cual (503 `busy`, el resultado no se confirma); cualquier otra
  `Exception` es fallo blando (S9-D30): log `derivación omitida` con los ids y
  `alert("athletes_derive_skipped", error_type=...)` en su propio `try`, sin ids.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.alerts import alert
from app.core.db import DatabaseBusy, translate_busy, violated_constraint
from app.core.events import EventDepthExceeded
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.records import current_rm
from app.modules.athletes.rules import RecordDraft, derive_rm
from app.modules.results import service as results_service
from app.modules.results.service import WodResultValidated
from app.modules.wods import service as wods_service

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


async def _derive(event: WodResultValidated, session: AsyncSession) -> None:
    """Todo el trabajo del handler (lecturas, reglas, récord, evento), DENTRO del savepoint."""
    mark = await results_service.get_mark(session, event.result_id)
    if mark is None or mark.status != "validated" or not mark.is_current:
        return
    if mark.validated_by is None:  # un validado siempre lo trae (CHECK `validated_pair`)
        logger.warning(
            "athletes: resultado validado sin validador",
            extra={"result_id": str(event.result_id), "member_id": str(event.member_id)},
        )
        return
    meta = (await wods_service.record_meta_for(session, [mark.wod_id])).get(mark.wod_id)
    # Sin vigente la regla es la más permisiva: si ni así deriva, no hace falta leer el vigente.
    if meta is None or derive_rm(mark, meta, None) is None:
        return
    if meta.primary_movement_id is None:  # lo garantiza derive_rm; el tipo lo exige
        return
    current = await current_rm(session, mark.member_id, meta.primary_movement_id)
    draft = derive_rm(mark, meta, current)
    if draft is None:
        return
    record = _record_of(draft, mark.member_id, mark.validated_by)
    session.add(record)
    await session.flush()
    await events.emit(
        PersonalRecordSet(
            record_id=record.id,
            member_id=mark.member_id,
            kind="rm",
            movement_id=draft.movement_id,
            benchmark_id=None,
            source="derived",
            achieved_on=draft.achieved_on,
        ),
        session,
    )


async def on_wod_result_validated(event: WodResultValidated, session: AsyncSession) -> None:
    """Deriva el RM del resultado recién validado (S9-D10). Un savepoint envuelve TODO (S9-D57)."""
    await session.flush()  # lo pendiente del emisor falla cerrado, FUERA del savepoint
    try:
        async with session.begin_nested():
            await _derive(event, session)
    except (DatabaseBusy, EventDepthExceeded):
        raise
    except DBAPIError as error:
        if translate_busy(error) is not None:
            raise
        if isinstance(error, IntegrityError) and violated_constraint(error) == UQ_RESULT_KIND:
            return  # el evento llegó dos veces: no-op, sin alerta (US-181 CA6)
        _skip(event, error)
    except Exception as error:
        _skip(event, error)


def subscribe_handlers() -> None:
    """Suscribe los handlers al bus; `athletes/service.py` lo llama al importarse (S9-D7)."""
    events.subscribe(WodResultValidated, on_wod_result_validated)
