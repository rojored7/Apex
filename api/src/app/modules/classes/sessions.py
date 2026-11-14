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
from datetime import date, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.modules.classes.events import SessionGenerated
from app.modules.classes.models import ClassSession, ClassSlot
from app.modules.classes.rules import PlannedSession, planned_sessions

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
