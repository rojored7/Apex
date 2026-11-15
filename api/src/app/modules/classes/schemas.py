"""Contrato de franjas (S7-A2, US-155; S7-D9, S7-D19).

- `SlotCreate` (`extra="forbid"`): `weekdays` (1 a 7 enteros estrictos de 0 a 6), `start_time`
  `HH:MM` (hora de Bogotá), `duration_min` de 15 a 240, `capacity` de 1 a 100 (si falta toma
  `settings.classes.default_capacity`), `default_coach_id` (nulo = «Open box · sin coach»), `name`
  de 1 a 40 (`SafeText`) y `valid_from` (por defecto hoy en Bogotá).
- `SlotPatch` (`extra="forbid"`): todo opcional; `model_fields_set` distingue no enviado de `null`
  (`default_coach_id: null` pasa a «sin coach», `name: null` quita el nombre). Incluye `is_active`.
- `SlotOut`: la respuesta; `coach_name` sale de `auth.service.user_names_for` (nunca el correo).
- `SlotListQuery`: filtros de la lista (`is_active`, `weekday`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.core.validators import SafeText
from app.modules.classes.rules import (
    CAPACITY_MAX,
    CAPACITY_MIN,
    DURATION_MAX,
    DURATION_MIN,
    NAME_MAX_LENGTH,
    TIME_PATTERN,
    WEEKDAY_MAX,
    WEEKDAY_MIN,
)

VALID_FROM_MIN: Final = date(2020, 1, 1)
VALID_FROM_MAX: Final = date(2100, 12, 31)

Weekdays = Annotated[
    list[Annotated[StrictInt, Field(ge=WEEKDAY_MIN, le=WEEKDAY_MAX)]],
    Field(min_length=1, max_length=WEEKDAY_MAX + 1),
]
StartTime = Annotated[str, Field(pattern=TIME_PATTERN.pattern)]
DurationMin = Annotated[StrictInt, Field(ge=DURATION_MIN, le=DURATION_MAX)]
Capacity = Annotated[StrictInt, Field(ge=CAPACITY_MIN, le=CAPACITY_MAX)]
SlotName = Annotated[SafeText, Field(min_length=1, max_length=NAME_MAX_LENGTH)]
ValidFrom = Annotated[date, Field(ge=VALID_FROM_MIN, le=VALID_FROM_MAX)]


class SlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    weekdays: Weekdays
    start_time: StartTime
    duration_min: DurationMin
    capacity: Capacity | None = None
    default_coach_id: UUID | None = None
    name: SlotName | None = None
    valid_from: ValidFrom | None = None


class SlotPatch(BaseModel):
    """`PATCH /class-slots/{slot_id}`: un campo ausente no es un cambio (`model_fields_set`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    weekdays: Weekdays | None = None
    start_time: StartTime | None = None
    duration_min: DurationMin | None = None
    capacity: Capacity | None = None
    default_coach_id: UUID | None = None
    name: SlotName | None = None
    valid_from: ValidFrom | None = None
    is_active: StrictBool | None = None


class SlotOut(BaseModel):
    id: UUID
    name: str | None
    weekdays: list[int]
    start_time: str
    duration_min: int
    capacity: int
    default_coach_id: UUID | None
    coach_name: str | None
    valid_from: date
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SlotListQuery(BaseModel):
    """Filtros de la lista; el router los arma desde la query string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_active: bool | None = None
    weekday: Annotated[int, Field(ge=WEEKDAY_MIN, le=WEEKDAY_MAX)] | None = None


SessionStatus = Literal["scheduled", "cancelled", "done"]
SessionName = SlotName
CancelReason = Annotated[SafeText, Field(min_length=1, max_length=200)]


class SessionCreate(BaseModel):
    """`POST /class-sessions` (sesión extra, `slot_id` nulo; S7-D11, L-1)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    starts_at: AwareDatetime
    duration_min: DurationMin
    capacity: Capacity | None = None
    coach_id: UUID | None = None
    name: SessionName | None = None


class SessionCancel(BaseModel):
    """`POST /class-sessions/{id}/cancel`: el motivo es obligatorio."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: CancelReason


class CancelFutureOut(BaseModel):
    """`POST /class-slots/{id}/cancel-future-sessions`: cuántas sesiones se cancelaron."""

    cancelled_count: int


class AttendeeOut(BaseModel):
    """Un asistente de la sesión (llega con C1; hoy la lista va vacía)."""

    id: UUID
    member_id: UUID
    first_name: str
    last_name: str
    flagged: bool
    flags: list[str]
    checked_in_at: datetime


class SessionOut(BaseModel):
    id: UUID
    slot_id: UUID | None
    session_date: date
    starts_at: datetime
    duration_min: int
    capacity: int
    coach_id: UUID | None
    coach_name: str | None
    name: str | None
    status: SessionStatus
    attendance_count: int
    cancel_reason: str | None
    cancelled_at: datetime | None


class SessionDetail(SessionOut):
    attendees: list[AttendeeOut]


class SessionListQuery(BaseModel):
    """Filtros de la lista: `week` o `from`/`to` (no ambos), `coach_id` y `status`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    coach_id: UUID | None = None
    status: SessionStatus | None = None


# Check-in (S7-C1, US-159; S7-D6, S7-D12, L-1) -----------------------------------------------


class AttendanceCreate(BaseModel):
    """`POST /attendance`: solo la sesión y el socio. `extra="forbid"` (L-1): el cliente nunca
    manda `membership_id`, `flags` ni `checked_in_at`; los decide el servidor."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    member_id: UUID


class CheckinOut(BaseModel):
    """201 del check-in. `flagged` se deriva de `flags` (`len(flags) > 0`)."""

    id: UUID
    flags: list[str]
    flagged: bool
    membership_status_at_checkin: str
    attendance_count: int
    capacity: int


class AttendanceRowOut(BaseModel):
    """Una fila de `GET /attendance`: nombre y apellido en claro, nunca campos cifrados."""

    id: UUID
    session_id: UUID
    session_date: date
    session_starts_at: datetime
    member_id: UUID
    first_name: str | None
    last_name: str | None
    membership_status_at_checkin: str
    flags: list[str]
    flagged: bool
    checked_in_at: datetime


class AttendanceListQuery(BaseModel):
    """Filtros de `GET /attendance` ya validados por el router."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    member_id: UUID | None = None
    session_id: UUID | None = None
    flagged: bool | None = None
    from_at: AwareDatetime | None = None
    to_at: AwareDatetime | None = None
    q: str | None = None


@dataclass(frozen=True, slots=True)
class CheckinMembership:
    """Lo que `classes` sabe de la membresía del socio en `on_date` (puerto de S7-D6).

    `status` es uno de `rules.MEMBERSHIP_STATUSES`; `membership_id` es nulo sin membresía vigente
    (estado `none`)."""

    membership_id: UUID | None
    status: str
    plan_name: str | None
    end_date: date | None
    classes_remaining: int | None
