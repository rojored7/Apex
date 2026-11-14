"""Tabla `classes.class_slots` (S7-A2, US-155; migración `0026_class_slots`; S7-D9).

- Comunes (`id`, `created_at`, `updated_at`, `created_by`).
- `weekdays` (`smallint[]`, de 1 a 7 días de 0 lunes a 6 domingo; el service los guarda sin repetir
  y ordenados), `start_time` (hora local de Bogotá, N-40), `duration_min` (15 a 240), `capacity`
  (1 a 100), `default_coach_id` (nulo = «Open box · sin coach»; sin FK entre esquemas), `name`
  (nulo o de 1 a 40), `valid_from` e `is_active`.
- `__audited__`: cada alta y cada cambio dejan su fila en `audit.audit_log` con antes y después.

[DECISIÓN DE DISEÑO] `start_time` es `time` en la base y `str` `HH:MM` en el ORM (`LocalTime`): el
serializador canónico de la auditoría (ADR-004) no admite `datetime.time` y no se toca; así el
antes y el después de un cambio de hora quedan en la cadena como texto.
"""

from __future__ import annotations

from datetime import date, time
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, Index, Integer, SmallInteger, Text, text
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
