"""Sesiones de clase (S7-B1, US-156; S7-D10). Privado del módulo: se usa por `service.py`.

- `generate_sessions(session, *, today, days=14, slot_ids=None, by=None) -> GenerateResult`: bajo
  `pg_advisory_xact_lock(4_270_006)` lee las franjas activas (todas o `slot_ids`), calcula con
  `rules.planned_sessions` las sesiones de `today` a `today + days - 1`, lee las que ya existen en
  ese rango en CUALQUIER estado (una `cancelled` no se regenera, US-156 CA5) e inserta por ORM solo
  las que faltan (auditadas; `created_by` es `by` o el actor del contexto, `SYSTEM_USER_ID` en el
  job). Emite `SessionGenerated` por cada una, en la misma transacción. Idempotente: el índice
  único `(slot_id, starts_at)` es la red de seguridad si el candado fallara. No confirma.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.modules.auth import service as auth_service
from app.modules.classes.events import SessionCancelled, SessionGenerated
from app.modules.classes.exceptions import (
    CoachInvalid,
    LockedByResults,
    SessionAlreadyCancelled,
    SessionCancelledError,
    SessionDuplicate,
    SessionFinished,
    SessionNotFound,
    SlotNotFound,
)
from app.modules.classes.models import ClassSession, ClassSlot
from app.modules.classes.queries import attendance_counts, session_out
from app.modules.classes.result_link import results_port
from app.modules.classes.rules import (
    PlannedSession,
    local_date,
    planned_sessions,
    validate_extra_start,
)
from app.modules.classes.schemas import (
    CancelFutureOut,
    SessionCancel,
    SessionCreate,
    SessionOut,
    SessionPatch,
)
from app.modules.settings import service as settings_service
from app.modules.wods import service as wods_service

logger = logging.getLogger("app.classes")

GENERATE_SESSIONS_LOCK_KEY: Final = 4_270_006
"""Candado asesor de transacción de la generación (S7-D10); distinto de 4_270_001 a 4_270_005. Lo
toman el job, el comando y el alta de una franja; las cancelaciones masivas (B3) también."""
GENERATE_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(:k)"
DEFAULT_DAYS: Final = 14
MAX_DAYS: Final = 28


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """`created`: sesiones nuevas; `slots`: franjas activas consideradas."""

    created: int
    slots: int


async def take_generate_lock(session: AsyncSession) -> None:
    """Toma el candado de generación (4_270_006). Lo reentra quien ya lo tiene (misma conexión).

    Orden único de candados de `classes`: 4_270_005 (franjas), 4_270_006 (generación) y, al primer
    `flush` auditado, 4_270_002 (cadena de auditoría). El job y el comando toman 006 y luego 002;
    `create_slot` toma 005 y 006 ANTES de escribir (S7-B1b): nadie pide 006 con 002 en la mano."""
    await session.execute(text(GENERATE_LOCK_SQL), {"k": GENERATE_SESSIONS_LOCK_KEY})


async def _existing(
    session: AsyncSession, franjas: Sequence[ClassSlot], desde: date, hasta: date
) -> set[tuple[UUID | None, datetime]]:
    """`(slot_id, starts_at)` de las sesiones del rango en cualquier estado."""
    filas = await session.execute(
        select(ClassSession.slot_id, ClassSession.starts_at).where(
            ClassSession.slot_id.in_([f.id for f in franjas]),
            ClassSession.session_date.between(desde, hasta),
        )
    )
    return {(slot, inicio) for slot, inicio in filas.all()}


def _missing(
    planeadas: Sequence[PlannedSession],
    existentes: set[tuple[UUID | None, datetime]],
    autor: UUID,
) -> list[ClassSession]:
    """Las filas por insertar: las planeadas que no existen (en ningún estado)."""
    return [
        ClassSession(
            slot_id=p.slot_id,
            session_date=p.session_date,
            starts_at=p.starts_at,
            duration_min=p.duration_min,
            capacity=p.capacity,
            coach_id=p.coach_id,
            name=p.name,
            status="scheduled",
            created_by=autor,
        )
        for p in planeadas
        if (p.slot_id, p.starts_at) not in existentes
    ]


async def generate_sessions(
    session: AsyncSession,
    *,
    today: date,
    days: int = DEFAULT_DAYS,
    slot_ids: Sequence[UUID] | None = None,
    by: UUID | None = None,
) -> GenerateResult:
    """Crea las sesiones que faltan de `today` a `today + days - 1` (docstring del módulo)."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError("days debe estar entre 1 y 28")
    await take_generate_lock(session)
    consulta = select(ClassSlot).where(ClassSlot.is_active.is_(True))
    if slot_ids is not None:
        consulta = consulta.where(ClassSlot.id.in_(list(slot_ids)))
    franjas = list((await session.scalars(consulta.order_by(ClassSlot.id))).all())
    hasta = today + timedelta(days=days - 1)
    ahora = current_clock().now_utc()
    planeadas = planned_sessions(franjas, today, hasta, not_before=ahora) if franjas else []
    if not planeadas:
        return GenerateResult(created=0, slots=len(franjas))
    existentes = await _existing(session, franjas, today, hasta)
    nuevas = _missing(planeadas, existentes, by if by is not None else get_actor())
    session.add_all(nuevas)
    await session.flush()
    for sesion in nuevas:
        await events.emit(
            SessionGenerated(
                session_id=sesion.id, slot_id=sesion.slot_id, starts_at=sesion.starts_at
            ),
            session,
        )
    logger.info(
        "classes: sesiones generadas",
        extra={"creadas": len(nuevas), "franjas": len(franjas), "dias": days},
    )
    return GenerateResult(created=len(nuevas), slots=len(franjas))


async def create_extra(
    session: AsyncSession, data: SessionCreate, *, by: UUID, role: str
) -> SessionOut:
    """Sesión extra (`slot_id` nulo; US-157 CA4). `session_date` la calcula el servidor desde
    `starts_at` en Bogotá (S7-D37). Un coach solo se asigna a sí mismo o a nadie (L-3); el admin
    elige cualquier usuario activo con rol coach o admin (`coach_invalid`)."""
    ahora = current_clock().now_utc()
    validate_extra_start(data.starts_at, ahora)
    coach = data.coach_id
    if coach is not None and role != "admin" and coach != by:
        raise CoachInvalid()
    if coach is not None and coach != by and not await auth_service.is_active_staff(session, coach):
        raise CoachInvalid()
    await take_generate_lock(session)  # S7-D38: serializa dos altas iguales antes de comprobar
    inicio = data.starts_at.astimezone(UTC)
    repetida = await session.scalar(
        select(ClassSession.id)
        .where(
            ClassSession.slot_id.is_(None),
            ClassSession.status == "scheduled",
            ClassSession.starts_at == inicio,
            ClassSession.coach_id.is_(None) if coach is None else ClassSession.coach_id == coach,
        )
        .limit(1)
    )
    if repetida is not None:
        raise SessionDuplicate()
    capacidad = data.capacity
    if capacidad is None:
        capacidad = (await settings_service.classes(session)).default_capacity
    fila = ClassSession(
        slot_id=None,
        session_date=local_date(inicio),
        starts_at=inicio,
        duration_min=data.duration_min,
        capacity=capacidad,
        coach_id=coach,
        name=data.name,
        status="scheduled",
        created_by=by,
    )
    session.add(fila)
    await session.flush()
    logger.info("classes: sesión extra creada", extra={"session_id": str(fila.id)})
    return await _one_out(session, fila, ahora)


async def _one_out(session: AsyncSession, fila: ClassSession, ahora: datetime) -> SessionOut:
    nombres = await auth_service.user_names_for(session, [fila.coach_id]) if fila.coach_id else {}
    cuentas = await attendance_counts(session, [fila.id])
    por_dia = await wods_service.day_wod_ids(session, {fila.session_date})
    return session_out(fila, nombres, ahora, cuentas.get(fila.id, 0), por_dia)


async def cancel_session(
    session: AsyncSession, session_id: UUID, data: SessionCancel, *, by: UUID
) -> SessionOut:
    """Cancela una sesión con motivo (US-157 CA5, CA6). No borra nada ni toca asistencias.

    Una sesión que ya terminó da siempre 409 `session_finished` (S7-D32, L-5), incluso si ya
    estaba cancelada; una cancelada que no ha terminado, 409 `session_already_cancelled`.
    `SessionCancelled` no lleva el motivo (L-2); el motivo tampoco va al log."""
    fila = await session.scalar(
        select(ClassSession).where(ClassSession.id == session_id).with_for_update()
    )
    if fila is None:
        raise SessionNotFound()
    ahora = current_clock().now_utc()
    if ahora >= fila.starts_at + timedelta(minutes=fila.duration_min):
        raise SessionFinished()
    if fila.status == "cancelled":
        raise SessionAlreadyCancelled()
    if await results_port().session_has_current_results(session, fila.id):  # S8-D46
        raise LockedByResults(
            "La clase ya tiene resultados registrados: no se puede cancelar.", field=None
        )
    fila.status = "cancelled"
    fila.cancel_reason = data.reason
    fila.cancelled_by = by
    fila.cancelled_at = ahora
    await session.flush()
    await events.emit(
        SessionCancelled(session_id=fila.id, slot_id=fila.slot_id, starts_at=fila.starts_at),
        session,
    )
    logger.info("classes: sesión cancelada", extra={"session_id": str(fila.id)})
    return await _one_out(session, fila, ahora)


async def _lock_future_scheduled(
    session: AsyncSession, slot_id: UUID, ahora: datetime
) -> list[ClassSession]:
    """Las `scheduled` de la franja que aún no empiezan, con `FOR UPDATE` en orden (S7-D37)."""
    filas = await session.scalars(
        select(ClassSession)
        .where(
            ClassSession.slot_id == slot_id,
            ClassSession.status == "scheduled",
            ClassSession.starts_at > ahora,
        )
        .order_by(ClassSession.starts_at, ClassSession.id)
        .with_for_update()
    )
    return list(filas.all())


async def cancel_future_sessions(
    session: AsyncSession, slot_id: UUID, data: SessionCancel, *, by: UUID
) -> CancelFutureOut:
    """Cancela las sesiones `scheduled` de la franja que aún no empiezan (US-158, S7-D26, M-1).

    Orden de candados (S7-D37): primero 4_270_006 (el job puede estar generando), luego un único
    `SELECT ... FOR UPDATE ORDER BY starts_at, id` y recién después el primer `flush` auditado
    (4_270_002). Atómica: un fallo, incluido el de un suscriptor, revierte todas (la transacción
    es la del request). Las pasadas, las ya canceladas y las extras no se tocan. Emite un
    `SessionCancelled` por sesión, sin el motivo (L-2). Sin futuras responde 0."""
    await take_generate_lock(session)
    if await session.scalar(select(ClassSlot.id).where(ClassSlot.id == slot_id)) is None:
        raise SlotNotFound()
    ahora = current_clock().now_utc()
    filas = await _lock_future_scheduled(session, slot_id, ahora)
    # V7 (M-1, S8-D46): una futura con resultados vigentes (recepción los registra antes de que
    # empiece) no se cancela; la franja entera queda intacta (409, no se salta en silencio).
    if filas and await results_port().sessions_with_current_results(session, [f.id for f in filas]):
        raise LockedByResults(
            "Una de las clases futuras ya tiene resultados registrados: no se puede cancelar.",
            field=None,
        )
    for fila in filas:
        fila.status = "cancelled"
        fila.cancel_reason = data.reason
        fila.cancelled_by = by
        fila.cancelled_at = ahora
    await session.flush()
    for fila in filas:
        await events.emit(
            SessionCancelled(session_id=fila.id, slot_id=fila.slot_id, starts_at=fila.starts_at),
            session,
        )
    logger.info(
        "classes: sesiones futuras canceladas",
        extra={"slot_id": str(slot_id), "canceladas": len(filas)},
    )
    return CancelFutureOut(cancelled_count=len(filas))


async def assign_wod(
    session: AsyncSession, session_id: UUID, data: SessionPatch, *, by: UUID
) -> SessionOut:
    """`PATCH /class-sessions/{id}` (S8-D9, S8-D36): asigna un WOD a la sesión o, con `null`, vuelve
    a heredar el del día.

    Orden de candados (M-6): la sesión `FOR UPDATE` ANTES de leer el WOD y de escribir, el mismo
    candado que toman las cancelaciones, el check-in y el registro de resultados. Una sesión
    cancelada da 409 `session_cancelled`; un `wod_id` inexistente, 422 `field = "wod_id"`. Sin
    cambio no hay `flush` ni fila de auditoría. Con resultados vigentes de la sesión, cambiar el WOD
    efectivo da 409 `locked_by_results` (M-2 de la revisión de A4); asignar en una sesión ya
    terminada (`done`) sí se permite mientras no tenga resultados."""
    fila = await session.scalar(
        select(ClassSession)
        .where(ClassSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fila is None:
        raise SessionNotFound()
    if fila.status == "cancelled":
        raise SessionCancelledError()
    if data.wod_id is not None:
        await wods_service.ensure_wod(session, data.wod_id)
    if fila.wod_id != data.wod_id:
        del_dia = (await wods_service.day_wod_ids(session, {fila.session_date})).get(
            fila.session_date
        )
        if (fila.wod_id or del_dia) != (
            data.wod_id or del_dia
        ) and await results_port().session_has_current_results(session, fila.id):
            raise LockedByResults()
        fila.wod_id = data.wod_id
        await session.flush()
        logger.info(
            "classes: wod de la sesión asignado",
            extra={"session_id": str(fila.id), "actor": str(by)},
        )
    return await _one_out(session, fila, current_clock().now_utc())
