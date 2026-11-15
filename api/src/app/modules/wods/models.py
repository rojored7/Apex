"""Tabla `wods.movements` (S8-A1, US-165; migración `0032_wods_movements`; S8-D5).

- Comunes (`id`, `created_at`, `updated_at`, `created_by`).
- `name` (1 a 60), `name_norm` (`rules.normalize_movement_name`; índice único), `category`
  (`weightlifting|gymnastics|monostructural|other`), `unit` (`kg|reps|m|cal|s`: qué se mide) e
  `is_active`.
- `__audited__`: cada alta y cada cambio dejan su fila en `audit.audit_log` con antes y después.
No se borra (RN-14): se desactiva; los triggers de la base también lo prohíben.
"""

from __future__ import annotations

from typing import ClassVar, Final

from sqlalchemy import Boolean, CheckConstraint, Index, Text, text
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
