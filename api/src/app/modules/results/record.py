"""Registrar un resultado (S8-B1, US-169; S8-D11, S8-D36, S8-D41; M-5, M-6, L-2, L-3). Privado.

`record_result(session, data, by=..., source=...)` hace todo `PUT /results` en una transacción y en
el orden único de candados (S8-D36, documentado en `core/locks.py`):
1. `members.ensure_exists` (404); 2. `lock_member`; 3. `ensure_exists` otra vez (la baja entre los
dos pasos da 404, L-3);
4. con `session_id`: la sesión `FOR SHARE` (`classes.session_for_result`: `scheduled`, 409
   `session_cancelled` aunque tenga asistencias; asistencia viva, 422
   `field = "session_id"`); su WOD
   efectivo debe ser `wod_id` (422 `session_id`);
5. el WOD `FOR SHARE` (`wods.scoring_for`: 404; `none` da 422 `wod_not_scored`); un WOD heredado por
   la sesión debe seguir siendo del día de la sesión (M-3); sin sesión, un WOD de fecha futura da
   422 `field = "wod_id"` (L-3);
6. `validate_score` (pura); 7. el vigente `FOR UPDATE` y las reglas de `supersedes_id`;
8. apagar el anterior, `flush` e `INSERT` en `begin_nested` (el 23505 sale como 409).
El resultado nace `validated` con `recorded_by = validated_by = by` (N-42): lo registra un coach o
el admin. `source` es `desk` o `kiosk` (M-1); lo decide el router, nunca el cuerpo.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.db import violated_constraint
from app.core.errors import ForbiddenError
from app.core.locks import lock_member
from app.modules.classes import service as classes_service
from app.modules.members import service as members_service
from app.modules.results.events import WodResultRecorded, WodResultValidated
from app.modules.results.exceptions import (
    InvalidSupersedes,
    ResultExists,
    ResultValidationError,
    WodNotScored,
)
from app.modules.results.models import UQ_CURRENT, UQ_SUPERSEDES, WodResult
from app.modules.results.rules import ScoreValues, validate_score
from app.modules.results.schemas import ResultIn, ResultOut
from app.modules.wods import service as wods_service

logger = logging.getLogger("app.results")

SOURCES: Final = ("desk", "kiosk")
KIOSK_SESSION_REQUIRED: Final = "En modo quiosco indica la clase (`session_id`)."
KIOSK_CORRECTION_MESSAGE: Final = (
    "En modo quiosco solo corriges los resultados que registraste en esta clase."
)


async def _current(session: AsyncSession, wod_id: UUID, member_id: UUID) -> WodResult | None:
    return await session.scalar(
        select(WodResult)
        .where(
            WodResult.wod_id == wod_id,
            WodResult.member_id == member_id,
            WodResult.is_current,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _insert(session: AsyncSession, fila: WodResult) -> None:
    """El `INSERT` en un savepoint: el 23505 de cualquiera de los dos únicos es 409."""
    try:
        async with session.begin_nested():
            session.add(fila)
            await session.flush()
    except IntegrityError as error:
        nombre = violated_constraint(error)
        if nombre == UQ_CURRENT:
            vigente = await session.scalar(
                select(WodResult.id).where(
                    WodResult.wod_id == fila.wod_id,
                    WodResult.member_id == fila.member_id,
                    WodResult.is_current,
                )
            )
            raise ResultExists(vigente) from None
        if nombre == UQ_SUPERSEDES:
            raise InvalidSupersedes() from None
        raise


async def _checked_targets(
    session: AsyncSession, data: ResultIn, source: str
) -> tuple[classes_service.ResultSession | None, wods_service.WodScoring]:
    """Pasos 1 a 5 del orden de candados: socio, sesión y WOD, con sus reglas. En quiosco (S8-D31)
    la clase es obligatoria y de hoy o de ayer."""
    if source == "kiosk":
        if data.session_id is None:
            raise ResultValidationError(message=KIOSK_SESSION_REQUIRED, field="session_id")
        await classes_service.ensure_kiosk_session(session, data.session_id)
    await members_service.ensure_exists(session, data.member_id)
    await lock_member(session, data.member_id)
    await members_service.ensure_exists(session, data.member_id)  # L-3
    clase = None
    if data.session_id is not None:
        clase = await classes_service.session_for_result(session, data.session_id, data.member_id)
        if clase.wod_id != data.wod_id:
            raise ResultValidationError(
                message="El WOD de esa clase no es el que se registra.", field="session_id"
            )
    wod = await wods_service.scoring_for(session, data.wod_id)
    if wod.score_type == "none":
        raise WodNotScored()
    if clase is not None:
        if clase.inherited and wod.date != clase.session_date:  # M-3
            raise ResultValidationError(
                message="El WOD de esa clase cambió de fecha.", field="session_id"
            )
    elif wod.date > current_clock().today_bogota():  # L-3
        raise ResultValidationError(message="El WOD todavía no ocurre.", field="wod_id")
    return clase, wod


async def _turn_off_previous(session: AsyncSession, data: ResultIn, source: str) -> None:
    """Paso 7 y 8 (primera mitad): el vigente `FOR UPDATE`; sin `supersedes_id` no puede haberlo
    (409 `result_exists`); con él, debe ser ese y se apaga antes del `INSERT`."""
    vigente = await _current(session, data.wod_id, data.member_id)
    if data.supersedes_id is None:
        if vigente is not None:
            raise ResultExists(vigente.id)
        return
    if vigente is None or vigente.id != data.supersedes_id:
        raise InvalidSupersedes()
    if source == "kiosk" and (vigente.source != "kiosk" or vigente.session_id != data.session_id):
        raise ForbiddenError("kiosk_mode", KIOSK_CORRECTION_MESSAGE)  # S8-D31
    if data.session_id != vigente.session_id:  # M-3: la corrección conserva su clase
        raise ResultValidationError(
            message="La corrección debe ser de la misma clase que el resultado.",
            field="session_id",
        )
    vigente.is_current = False
    await session.flush()


def _new_row(
    data: ResultIn, wod: wods_service.WodScoring, score: ScoreValues, *, by: UUID, source: str
) -> WodResult:
    ahora = _aware(current_clock().now_utc())
    return WodResult(
        wod_id=data.wod_id,
        member_id=data.member_id,
        session_id=data.session_id,
        wod_date=wod.date,
        benchmark_id=wod.benchmark_id,
        level=data.level,
        seconds=score.seconds,
        rounds=score.rounds,
        reps=score.reps,
        load_g=score.load_g,
        capped=score.capped,
        scaled_movement_ids=list(score.scaled_movement_ids),
        status="validated",
        recorded_by=by,
        validated_by=by,
        validated_at=ahora,
        supersedes_id=data.supersedes_id,
        is_current=True,
        source=source,
        created_by=by,
    )


async def record_result(
    session: AsyncSession, data: ResultIn, *, by: UUID, source: str = "desk"
) -> ResultOut:
    _clase, wod = await _checked_targets(session, data, source)
    score = validate_score(
        score_type=wod.score_type,
        time_cap_s=wod.time_cap_s,
        level=data.level,
        seconds=data.seconds,
        rounds=data.rounds,
        reps=data.reps,
        load_g=data.load_g,
        capped=data.capped,
        scaled_movement_ids=data.scaled_movement_ids,
        wod_movement_ids=wod.movement_ids,
    )
    await _turn_off_previous(session, data, source)
    fila = _new_row(data, wod, score, by=by, source=source)
    await _insert(session, fila)
    recorded = WodResultRecorded(
        result_id=fila.id,
        member_id=fila.member_id,
        wod_id=fila.wod_id,
        level=fila.level,
        load_g=fila.load_g,
        primary_movement_id=wod.primary_movement_id,
    )
    await events.emit(recorded, session)
    validated = WodResultValidated(result_id=fila.id, member_id=fila.member_id, wod_id=fila.wod_id)
    await events.emit(validated, session)
    logger.info(
        "results: resultado registrado",
        extra={
            "result_id": str(fila.id),
            "source": source,
            "corrige": data.supersedes_id is not None,
        },
    )
    return ResultOut.model_validate(fila)


def _aware(valor: datetime) -> datetime:
    return valor if valor.tzinfo is not None else valor.replace(tzinfo=UTC)


async def session_has_current_results(session: AsyncSession, session_id: UUID) -> bool:
    """El puerto de `classes` (M-2): ¿hay resultados vigentes registrados desde esa sesión?"""
    hallado = await session.scalar(
        select(WodResult.id)
        .where(WodResult.session_id == session_id, WodResult.is_current)
        .limit(1)
    )
    return hallado is not None


async def sessions_with_current_results(
    session: AsyncSession, session_ids: Sequence[UUID]
) -> set[UUID]:
    """El puerto de `classes` (V7, M-1): de esas sesiones, las que tienen resultados vigentes."""
    if not session_ids:
        return set()
    filas = await session.scalars(
        select(WodResult.session_id)
        .where(WodResult.session_id.in_(list(session_ids)), WodResult.is_current)
        .distinct()
    )
    return {fila for fila in filas.all() if fila is not None}


async def member_has_current_result_in_session(
    session: AsyncSession, session_id: UUID, member_id: UUID
) -> bool:
    """El puerto de `classes` (S8-D46): ¿ese socio tiene un resultado vigente de esa sesión?"""
    hallado = await session.scalar(
        select(WodResult.id)
        .where(
            WodResult.session_id == session_id,
            WodResult.member_id == member_id,
            WodResult.is_current,
        )
        .limit(1)
    )
    return hallado is not None
