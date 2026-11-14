"""Franjas del horario (S7-A2, US-155; S7-D9, S7-D7). Privado del módulo: se usa por `service.py`.

- `create_slot(session, data, by) -> SlotOut`: valida (`rules.validate_slot`), exige coach activo
  con rol `coach` o `admin` si viene (422 `coach_invalid`, `auth.service.is_active_staff`), toma el
  cupo por defecto de `settings.classes` si falta, y comprueba bajo `CLASS_SLOTS_LOCK_KEY` que no
  haya otra franja activa con un día y la hora de inicio en común (409 `slot_conflict`); al
  final genera sus sesiones de los próximos 14 días (B1, `sessions.generate_sessions`).
- `update_slot(session, slot_id, patch, by) -> SlotOut`: `FOR UPDATE` de la franja, aplica solo lo
  enviado (`model_fields_set`), vuelve a validar y a comprobar el choque si queda activa. Nunca
  toca sesiones ya generadas (Q23). Sin cambios no hay `flush` ni auditoría.
- `list_slots(session, filters, page)` y `get_slot(session, slot_id)`.
No hay borrado: se pausan con `is_active = false` (RN-14; los triggers también lo prohíben).
"""

from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Text, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.auth import service as auth_service
from app.modules.classes.exceptions import (
    ClassValidationError,
    CoachInvalid,
    SlotConflict,
    SlotNotFound,
)
from app.modules.classes.models import ClassSlot
from app.modules.classes.rules import normalize_weekdays, slots_overlap, validate_slot
from app.modules.classes.schemas import SlotCreate, SlotListQuery, SlotOut, SlotPatch
from app.modules.classes.sessions import generate_sessions
from app.modules.settings import service as settings_service

logger = logging.getLogger("app.classes")

CLASS_SLOTS_LOCK_KEY: Final = 4_270_005
"""Candado asesor de transacción de las escrituras de franjas (S7-D9); distinto de 4_270_001 a
4_270_004. Escriben solo admin y rara vez."""
SLOT_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(:k)"

_EDITABLES: Final[tuple[str, ...]] = (
    "weekdays",
    "start_time",
    "duration_min",
    "capacity",
    "default_coach_id",
    "name",
    "valid_from",
    "is_active",
)
_OBLIGATORIOS: Final[frozenset[str]] = frozenset(
    {"weekdays", "start_time", "duration_min", "capacity", "valid_from", "is_active"}
)
"""Los que no admiten `null` explícito en el `PATCH` (solo coach y nombre son anulables)."""


async def _lock(session: AsyncSession) -> None:
    await session.execute(text(SLOT_LOCK_SQL), {"k": CLASS_SLOTS_LOCK_KEY})


def _out(slot: ClassSlot, coach_names: dict[UUID, str]) -> SlotOut:
    coach = slot.default_coach_id
    return SlotOut(
        id=slot.id,
        name=slot.name,
        weekdays=list(slot.weekdays),
        start_time=slot.start_time,
        duration_min=slot.duration_min,
        capacity=slot.capacity,
        default_coach_id=coach,
        coach_name=coach_names.get(coach) if coach is not None else None,
        valid_from=slot.valid_from,
        is_active=slot.is_active,
        created_at=slot.created_at,
        updated_at=slot.updated_at,
    )


async def _outs(session: AsyncSession, slots: list[ClassSlot]) -> list[SlotOut]:
    """`SlotOut` de cada franja con los nombres de coach en una sola consulta."""
    ids = [s.default_coach_id for s in slots if s.default_coach_id is not None]
    nombres = await auth_service.user_names_for(session, ids) if ids else {}
    return [_out(s, nombres) for s in slots]


async def _ensure_coach(session: AsyncSession, coach_id: UUID | None) -> None:
    if coach_id is not None and not await auth_service.is_active_staff(session, coach_id):
        raise CoachInvalid()


async def _ensure_no_conflict(
    session: AsyncSession, *, weekdays: list[int], start_time: str, exclude: UUID | None
) -> None:
    """409 `slot_conflict` si otra franja activa comparte un día y la hora de inicio."""
    consulta = select(ClassSlot).where(
        ClassSlot.is_active.is_(True),
        ClassSlot.start_time == start_time,
        ClassSlot.weekdays.overlap(weekdays),
    )
    if exclude is not None:
        consulta = consulta.where(ClassSlot.id != exclude)
    for otra in (await session.scalars(consulta.order_by(ClassSlot.id))).all():
        if slots_overlap(weekdays, start_time, otra.weekdays, otra.start_time):
            raise SlotConflict(existing_id=otra.id)


async def create_slot(session: AsyncSession, data: SlotCreate, by: UUID) -> SlotOut:
    """Alta de una franja activa (US-155)."""
    dias = normalize_weekdays(data.weekdays)
    capacidad = data.capacity
    if capacidad is None:
        capacidad = (await settings_service.classes(session)).default_capacity
    validate_slot(data.weekdays, data.start_time, data.duration_min, capacidad)
    await _ensure_coach(session, data.default_coach_id)
    await _lock(session)
    await _ensure_no_conflict(session, weekdays=dias, start_time=data.start_time, exclude=None)
    slot = ClassSlot(
        weekdays=dias,
        start_time=data.start_time,
        duration_min=data.duration_min,
        capacity=capacidad,
        default_coach_id=data.default_coach_id,
        name=data.name,
        valid_from=data.valid_from or current_clock().today_bogota(),
        is_active=True,
        created_by=by,
    )
    session.add(slot)
    await session.flush()  # `eager_defaults`: fechas ya cargadas
    # S7-D9/D10: la semana no queda vacía hasta las 07:00 del día siguiente; el candado de
    # generación (4_270_006) se toma DESPUÉS del de franjas (4_270_005): nadie los toma al revés.
    await generate_sessions(
        session, today=current_clock().today_bogota(), slot_ids=[slot.id], by=by
    )
    logger.info("classes: franja creada", extra={"slot_id": str(slot.id)})
    return (await _outs(session, [slot]))[0]


async def _locked_slot(session: AsyncSession, slot_id: UUID) -> ClassSlot:
    slot = await session.scalar(select(ClassSlot).where(ClassSlot.id == slot_id).with_for_update())
    if slot is None:
        raise SlotNotFound()
    return slot


def _merged(slot: ClassSlot, patch: SlotPatch) -> dict[str, Any]:
    """Los valores resultantes de los campos editables; `null` explícito solo en los anulables."""
    valores: dict[str, Any] = {campo: getattr(slot, campo) for campo in _EDITABLES}
    for campo in patch.model_fields_set & set(_EDITABLES):
        valor = getattr(patch, campo)
        if valor is None and campo in _OBLIGATORIOS:
            raise ClassValidationError(message="Este campo no puede quedar vacío.", field=campo)
        valores[campo] = valor
    return valores


async def update_slot(session: AsyncSession, slot_id: UUID, patch: SlotPatch, by: UUID) -> SlotOut:
    """`PATCH` de una franja (US-155 CA5, CA6): solo lo enviado; nunca toca sesiones."""
    await _lock(session)
    slot = await _locked_slot(session, slot_id)
    valores = _merged(slot, patch)
    valores["weekdays"] = normalize_weekdays(valores["weekdays"])
    validate_slot(
        valores["weekdays"], valores["start_time"], valores["duration_min"], valores["capacity"]
    )
    if "default_coach_id" in patch.model_fields_set:
        await _ensure_coach(session, valores["default_coach_id"])
    cambios = {c: v for c, v in valores.items() if getattr(slot, c) != v}
    if not cambios:
        return (await _outs(session, [slot]))[0]
    if valores["is_active"]:
        await _ensure_no_conflict(
            session,
            weekdays=valores["weekdays"],
            start_time=valores["start_time"],
            exclude=slot.id,
        )
    for campo, valor in cambios.items():
        setattr(slot, campo, valor)
    await session.flush()
    logger.info(
        "classes: franja editada",
        extra={"slot_id": str(slot.id), "changed_fields": sorted(cambios), "actor": str(by)},
    )
    return (await _outs(session, [slot]))[0]


async def get_slot(session: AsyncSession, slot_id: UUID) -> SlotOut:
    slot = await session.get(ClassSlot, slot_id)
    if slot is None:
        raise SlotNotFound()
    return (await _outs(session, [slot]))[0]


async def list_slots(
    session: AsyncSession, filters: SlotListQuery, page: PageParams, *, q: str | None = None
) -> Page[SlotOut]:
    """`GET /class-slots`: `q` (nombre, sin tildes ni mayúsculas), `is_active` y `weekday`
    (contiene el día); orden por hora."""
    consulta = select(ClassSlot)
    termino = clean_query(q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(
            sql_fold(func.coalesce(ClassSlot.name, "")).ilike(patron, escape=LIKE_ESCAPE)
        )
    if filters.is_active is not None:
        consulta = consulta.where(ClassSlot.is_active.is_(filters.is_active))
    if filters.weekday is not None:
        consulta = consulta.where(ClassSlot.weekdays.contains([filters.weekday]))
    slots, total = await paginate(
        session, consulta.order_by(ClassSlot.start_time, ClassSlot.id), page
    )
    return to_page(await _outs(session, slots), total, page)
