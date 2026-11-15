"""Tabla `wods.movements` (S8-A1, US-165; migración `0032_wods_movements`; S8-D5).

- Comunes (`id`, `created_at`, `updated_at`, `created_by`).
- `name` (1 a 60), `name_norm` (`rules.normalize_movement_name`; índice único), `category`
  (`weightlifting|gymnastics|monostructural|other`), `unit` (`kg|reps|m|cal|s`: qué se mide) e
  `is_active`.
- `__audited__`: cada alta y cada cambio dejan su fila en `audit.audit_log` con antes y después.
No se borra (RN-14): se desactiva; los triggers de la base también lo prohíben.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

SCHEMA: Final = "wods"
CATEGORY_CHECK: Final = "category IN ('weightlifting', 'gymnastics', 'monostructural', 'other')"
UNIT_CHECK: Final = "unit IN ('kg', 'reps', 'm', 'cal', 's')"


class Movement(CommonColumnsMixin, Base):
    __tablename__ = "movements"
    __table_args__ = (
        CheckConstraint(CATEGORY_CHECK, name="category"),
        CheckConstraint(UNIT_CHECK, name="unit"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="name_length"),
        CheckConstraint("char_length(name_norm) BETWEEN 1 AND 60", name="name_norm_length"),
        Index("uq_movements_name_norm", "name_norm", unique=True),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


BENCHMARK_SCORE_CHECK: Final = "score_type IN ('time', 'rounds_reps', 'reps', 'load')"


class Benchmark(CommonColumnsMixin, Base):
    """Tabla `wods.benchmarks` (S8-A2, US-166, N-46; migración `0033_wods_benchmarks`; S8-D6).

    Un WOD de referencia con nombre propio (Fran, Murph...): `name`, `name_norm` (la misma
    normalización que los movimientos; índice único), `description` (0 a 2.000) y `score_type`
    (`time|rounds_reps|reps|load`). Auditada; no se borra (RN-14): los triggers lo prohíben.
    """

    __tablename__ = "benchmarks"
    __table_args__ = (
        CheckConstraint(BENCHMARK_SCORE_CHECK, name="score_type"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="name_length"),
        CheckConstraint("char_length(name_norm) BETWEEN 1 AND 60", name="name_norm_length"),
        CheckConstraint("char_length(description) <= 2000", name="description_length"),
        Index("uq_benchmarks_name_norm", "name_norm", unique=True),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    score_type: Mapped[str] = mapped_column(Text, nullable=False)


WOD_SCORE_CHECK: Final = "score_type IN ('time', 'rounds_reps', 'reps', 'load', 'none')"
WOD_TIME_CAP_CHECK: Final = (
    "time_cap_s IS NULL OR "
    "(time_cap_s BETWEEN 1 AND 14400 AND score_type IN ('time', 'rounds_reps'))"
)


class Wod(CommonColumnsMixin, Base):
    """Tabla `wods.wods` (S8-A3, US-166; migración `0034_wods_wods`; S8-D7).

    Un WOD principal por día (`uq_wods_date`). `score_type = none` no admite resultados;
    `time_cap_s` (1 a 14.400) solo con `time|rounds_reps`; `benchmark_id` apunta a
    `wods.benchmarks` (`is_benchmark` se deriva). Auditada; no se borra (RN-14).
    """

    __tablename__ = "wods"
    __table_args__ = (
        CheckConstraint(WOD_SCORE_CHECK, name="score_type"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 80", name="title_length"),
        CheckConstraint("char_length(description) <= 2000", name="description_length"),
        CheckConstraint(WOD_TIME_CAP_CHECK, name="time_cap"),
        Index("uq_wods_date", "date", unique=True),
        Index("ix_wods_benchmark_id", "benchmark_id"),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    score_type: Mapped[str] = mapped_column(Text, nullable=False)
    time_cap_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    benchmark_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("wods.benchmarks.id", name="fk_wods_benchmark_id"), nullable=True
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )


class WodMovement(CommonColumnsMixin, Base):
    """Tabla `wods.wod_movements` (S8-A3, US-166; migración `0035_wods_wod_movements`).

    `movement_name` copia el nombre del catálogo al escribir. Cargas en gramos enteros
    (S8-D41). `DELETE` permitido (E6): los reemplazos de lista quedan auditados fila a fila.
    """

    __tablename__ = "wod_movements"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 30", name="position"),
        CheckConstraint("char_length(movement_name) BETWEEN 1 AND 60", name="movement_name_length"),
        CheckConstraint("char_length(reps) <= 40", name="reps_length"),
        CheckConstraint("char_length(notes) <= 200", name="notes_length"),
        CheckConstraint(
            "load_rx_m_g IS NULL OR load_rx_m_g BETWEEN 0 AND 1000000", name="load_rx_m_g"
        ),
        CheckConstraint(
            "load_rx_f_g IS NULL OR load_rx_f_g BETWEEN 0 AND 1000000", name="load_rx_f_g"
        ),
        Index("uq_wod_movements_wod_position", "wod_id", "position", unique=True),
        Index(
            "uq_wod_movements_primary",
            "wod_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_wod_movements_movement_id", "movement_id"),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True

    wod_id: Mapped[UUID] = mapped_column(
        ForeignKey("wods.wods.id", name="fk_wod_movements_wod_id"), nullable=False
    )
    movement_id: Mapped[UUID] = mapped_column(
        ForeignKey("wods.movements.id", name="fk_wod_movements_movement_id"), nullable=False
    )
    movement_name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    load_rx_m_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    load_rx_f_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
