"""Tabla `plans.plans` (S2-B9, US-078 y US-079; migración `0007_plans`; DECISIÓN 32, S2-D32).

- Comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at` (borrado lógico).
- `name` (texto no vacío tras `btrim`), `price_cop` (entero en COP, `> 0`), `kind` (`days` o
  `classes`), `duration_days` (`> 0`), `class_count` (nulo salvo en `classes`, donde es `> 0`) e
  `is_active` (default `true`).
- `uq_plans_name_alive`: único sobre `lower(btrim(name))` entre los vivos (`deleted_at IS
  NULL`): "Mensual" y "mensual" chocan y un plan dado de baja libera su nombre.
- `ix_plans_active_alive`: `is_active` entre los vivos (la lista del coach, S2-D26).
- `__audited__`: cada alta deja su fila `insert` en `audit.audit_log`.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin, SoftDeleteMixin

KINDS: tuple[str, ...] = ("days", "classes")
NAME_ALIVE_INDEX = "uq_plans_name_alive"


class Plan(CommonColumnsMixin, SoftDeleteMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price_cop > 0", name="price_cop_positive"),
        CheckConstraint("duration_days > 0", name="duration_days_positive"),
        CheckConstraint("kind IN ('days', 'classes')", name="kind"),
        # `IS NOT NULL` explícito: con solo `class_count > 0`, un NULL deja la expresión en NULL y
        # el CHECK la acepta (`classes` sin clases entraría). Lo detectó la validación del Rojo.
        CheckConstraint(
            "(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0)"
            " OR (kind = 'days' AND class_count IS NULL)",
            name="class_count_by_kind",
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        {"schema": "plans"},
    )
    __audited__: ClassVar[bool] = True

    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    class_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


Index(
    NAME_ALIVE_INDEX,
    func.lower(func.btrim(Plan.name)),
    unique=True,
    postgresql_where=Plan.deleted_at.is_(None),
)
Index("ix_plans_active_alive", Plan.is_active, postgresql_where=Plan.deleted_at.is_(None))
