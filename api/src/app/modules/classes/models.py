"""Tablas `classes.class_slots` (S7-A2, US-155; migración `0026_class_slots`; S7-D9) y
`classes.class_sessions` (S7-B1, US-156; migración `0027_class_sessions`; S7-D10).

- Comunes (`id`, `created_at`, `updated_at`, `created_by`).
- `weekdays` (`smallint[]`, de 1 a 7 días de 0 lunes a 6 domingo; el service los guarda sin repetir
  y ordenados), `start_time` (hora local de Bogotá, N-40), `duration_min` (15 a 240), `capacity`
  (1 a 100), `default_coach_id` (nulo = «Open box · sin coach»; sin FK entre esquemas), `name`
  (nulo o de 1 a 40), `valid_from` e `is_active`.
- `__audited__`: cada alta y cada cambio dejan su fila en `audit.audit_log` con antes y después.

- `ClassSession`: una clase concreta. `slot_id` (FK RESTRICT a `class_slots`; nulo = sesión extra),
  `session_date` (fecha civil de Bogotá), `starts_at` (UTC), `duration_min`, `capacity`, `coach_id`,
  `name`, `wod_id` (nulo; EP-22, sin FK), `status` (`scheduled` o `cancelled`; `done` se calcula al
  leer) y `cancel_reason`, `cancelled_by`, `cancelled_at` (los tres juntos con `cancelled`).
  `__audited__`: cada alta y cada cancelación dejan su fila con antes y después.

[DECISIÓN DE DISEÑO] `start_time` es `time` en la base y `str` `HH:MM` en el ORM (`LocalTime`): el
serializador canónico de la auditoría (ADR-004) no admite `datetime.time` y no se toca; así el
antes y el después de un cambio de hora quedan en la cadena como texto.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy import Time as SqlTime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.db import Base, CommonColumnsMixin

SCHEMA: Final = "classes"


class LocalTime(TypeDecorator[str]):
    """`time` en PostgreSQL; `HH:MM` (`str`) en Python."""

    impl = SqlTime
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> time | None:
        return None if value is None else time.fromisoformat(value)

    def process_result_value(self, value: time | None, dialect: Dialect) -> str | None:
        return None if value is None else value.strftime("%H:%M")


class ClassSlot(CommonColumnsMixin, Base):
    __tablename__ = "class_slots"
    __table_args__ = (
        CheckConstraint(
            "cardinality(weekdays) BETWEEN 1 AND 7 "
            "AND weekdays <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]",
            name="weekdays",
        ),
        CheckConstraint("duration_min BETWEEN 15 AND 240", name="duration_min"),
        CheckConstraint("capacity BETWEEN 1 AND 100", name="capacity"),
        CheckConstraint("name IS NULL OR char_length(name) BETWEEN 1 AND 40", name="name_length"),
        Index("ix_class_slots_is_active", "is_active"),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    weekdays: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    start_time: Mapped[str] = mapped_column(LocalTime, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    default_coach_id: Mapped[UUID | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


SESSION_STATUSES: Final = ("scheduled", "cancelled")


class ClassSession(CommonColumnsMixin, Base):
    __tablename__ = "class_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="status"),
        CheckConstraint("duration_min BETWEEN 15 AND 240", name="duration_min"),
        CheckConstraint("capacity BETWEEN 1 AND 100", name="capacity"),
        CheckConstraint("name IS NULL OR char_length(name) BETWEEN 1 AND 40", name="name_length"),
        CheckConstraint(
            "cancel_reason IS NULL OR char_length(cancel_reason) BETWEEN 1 AND 200",
            name="cancel_reason_length",
        ),
        CheckConstraint(
            "(status = 'cancelled' AND cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancelled_at IS NOT NULL) OR (status = 'scheduled' AND cancel_reason IS NULL "
            "AND cancelled_by IS NULL AND cancelled_at IS NULL)",
            name="cancel_trio",
        ),
        CheckConstraint(
            "session_date = (starts_at AT TIME ZONE 'America/Bogota')::date",
            name="session_date_bogota",
        ),
        Index(
            "uq_class_sessions_slot_starts_at",
            "slot_id",
            "starts_at",
            unique=True,
            postgresql_where=text("slot_id IS NOT NULL"),
        ),
        Index("ix_class_sessions_starts_at", "starts_at"),
        Index("ix_class_sessions_session_date", "session_date"),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    slot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("classes.class_slots.id", ondelete="RESTRICT"), nullable=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    coach_id: Mapped[UUID | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    wod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="scheduled", server_default=text("'scheduled'")
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[UUID | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


MEMBERSHIP_STATUS_AT_CHECKIN: Final = (
    "active",
    "expiring",
    "expired",
    "frozen",
    "pending_payment",
    "none",
)
ATTENDANCE_FLAGS: Final = (
    "expired",
    "no_membership",
    "frozen",
    "pending_payment",
    "over_capacity",
    "out_of_window",
    "other_day",
)
ATTENDANCE_UNIQUE_ALIVE: Final = "uq_attendance_session_member_alive"


def _en_lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


class Attendance(CommonColumnsMixin, Base):
    """Asistencia de un socio a una sesión (S7-C1, US-159; migración `0028_attendance`; S7-D13).

    `member_id` sin FK entre esquemas; `membership_id` es la membresía que decidió (para devolver
    la clase, US-160); `flags` son las siete banderas; `flagged` se deriva (`len(flags) > 0`) y no
    se guarda. Borrado lógico: `removed_at`, `removed_by`, `removed_reason` (US-161); la guarda de
    la base solo deja pasar `removed_*` y `updated_at`, una vez. Sujeto: `member_id`."""

    __tablename__ = "attendance"
    __table_args__ = (
        CheckConstraint(
            f"membership_status_at_checkin IN ({_en_lista(MEMBERSHIP_STATUS_AT_CHECKIN)})",
            name="status_at_checkin",
        ),
        CheckConstraint(
            f"flags <@ ARRAY[{_en_lista(ATTENDANCE_FLAGS)}]::text[]",
            name="flags",
        ),
        CheckConstraint(
            "removed_reason IS NULL OR char_length(removed_reason) BETWEEN 1 AND 200",
            name="removed_reason_length",
        ),
        CheckConstraint(
            "(removed_at IS NULL AND removed_by IS NULL AND removed_reason IS NULL) "
            "OR (removed_at IS NOT NULL AND removed_by IS NOT NULL)",
            name="removed_pair",
        ),
        Index(
            ATTENDANCE_UNIQUE_ALIVE,
            "session_id",
            "member_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "ix_attendance_member_checked_in",
            "member_id",
            text("checked_in_at DESC"),
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "ix_attendance_checked_in",
            "checked_in_at",
            postgresql_where=text("removed_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("classes.class_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    member_id: Mapped[UUID] = mapped_column(nullable=False)
    membership_id: Mapped[UUID | None] = mapped_column(nullable=True)
    membership_status_at_checkin: Mapped[str] = mapped_column(Text, nullable=False)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_in_by: Mapped[UUID] = mapped_column(nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    removed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
