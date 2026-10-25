"""Tabla `memberships.memberships` (S3-B1, US-084; migración `0008_memberships`; D8, D9, S3-D48).

- `member_id` y `plan_id` sin FK (otros esquemas, regla de módulos 2); `agreed_price_cop` es el
  precio pactado (entero COP, RN-04) y no cambia nunca; `start_date` y `end_date` son fechas
  civiles de Bogotá con fin inclusivo (N-23); `classes_total` y `classes_remaining` solo en
  planes por clases (D15); `status` es uno de `STATUSES` (D5: se escribe en cada transición y
  solo se lee para `cancelled` y `pending_payment`); `cancel_reason`, `cancelled_by` y
  `cancelled_at` solo en una `cancelled` (CHECK `cancelled_has_reason` y, al revés,
  `cancel_fields_only_when_cancelled`).
- `ex_memberships_member_dates` (D8): dos membresías no canceladas del mismo socio no se solapan
  con `daterange(start_date, end_date, '[]')`; adyacentes (fin el 28, inicio el 29) sí caben.
- Sin `relationship()` (D6) y sin columnas diferidas (el hook lee `history.deleted`).
- `__audited__` con `__audit_subject__ = "member_id"` (G-05): la fila de auditoría lleva
  `subject_member_id` del socio.
- Los triggers de identidad y de borrado viven solo en la migración (`memberships.guard_identity`
  y `memberships.forbid_delete`, S3-D48 y S3-D49).

`memberships.membership_freezes` (S3-B2, US-089; migración `0009_membership_freezes`; D14, M-5):
una fila por congelación con `frozen_from`, `frozen_to` y `days = (frozen_to - frozen_from) + 1`
(RN-07), FK a `memberships.memberships` (mismo esquema). `ex_membership_freezes_dates`: dos
ventanas de la misma membresía no se cruzan. Solo se agregan filas: la función
`memberships.forbid_freeze_mutation()` rechaza cambiar, borrar o vaciar la tabla (`CONSTRAINT =
membership_freezes_append_only`). `__audited__` sin `__audit_subject__`: la tabla no tiene
`member_id`; la fila `update` de la membresía (fin y estado) sí lleva el socio. Se anota para
US-106 (Sprint 4A), que decide cómo mostrar las congelaciones en el historial.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

STATUSES: Final[tuple[str, ...]] = (
    "pending_payment",
    "active",
    "expiring",
    "expired",
    "frozen",
    "cancelled",
)
EXCLUDE_NAME: Final = "ex_memberships_member_dates"
IDENTITY_CONSTRAINT: Final = "memberships_identity"
NO_DELETE_CONSTRAINT: Final = "memberships_no_delete"
FREEZE_EXCLUDE_NAME: Final = "ex_membership_freezes_dates"
FREEZE_APPEND_ONLY_CONSTRAINT: Final = "membership_freezes_append_only"


class Membership(CommonColumnsMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("agreed_price_cop > 0", name="agreed_price_positive"),
        CheckConstraint("start_date <= end_date", name="dates_ordered"),
        CheckConstraint(
            "status IN ('pending_payment', 'active', 'expiring', 'expired', 'frozen', 'cancelled')",
            name="status",
        ),
        CheckConstraint("classes_total > 0", name="classes_total_positive"),
        CheckConstraint("classes_remaining >= 0", name="classes_remaining_non_negative"),
        CheckConstraint(
            "(classes_total IS NULL) = (classes_remaining IS NULL)", name="classes_pair"
        ),
        CheckConstraint("classes_remaining <= classes_total", name="classes_remaining_le_total"),
        CheckConstraint(
            "status <> 'cancelled' OR (cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancelled_at IS NOT NULL)",
            name="cancelled_has_reason",
        ),
        CheckConstraint(
            "status = 'cancelled' OR (cancel_reason IS NULL AND cancelled_by IS NULL "
            "AND cancelled_at IS NULL)",
            name="cancel_fields_only_when_cancelled",
        ),
        CheckConstraint(
            "cancel_reason IS NULL OR char_length(cancel_reason) BETWEEN 5 AND 500",
            name="cancel_reason_length",
        ),
        ExcludeConstraint(
            ("member_id", "="),
            (literal_column("daterange(start_date, end_date, '[]')"), "&&"),
            name=EXCLUDE_NAME,
            using="gist",
            where=text("status <> 'cancelled'"),
        ),
        Index("ix_memberships_status_end_date", "status", "end_date"),
        Index("ix_memberships_member_status_start", "member_id", "status", "start_date"),
        Index("ix_memberships_plan_id", "plan_id"),
        {"schema": "memberships"},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    member_id: Mapped[UUID] = mapped_column(nullable=False)
    plan_id: Mapped[UUID] = mapped_column(nullable=False)
    agreed_price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    classes_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classes_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[UUID | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MembershipFreeze(CommonColumnsMixin, Base):
    """Una congelación de una membresía (S3-B2, D14): ventana cerrada y sus días (RN-07)."""

    __tablename__ = "membership_freezes"
    __table_args__ = (
        CheckConstraint("frozen_from <= frozen_to", name="dates_ordered"),
        CheckConstraint("days = (frozen_to - frozen_from) + 1", name="days_match"),
        ExcludeConstraint(
            ("membership_id", "="),
            (literal_column("daterange(frozen_from, frozen_to, '[]')"), "&&"),
            name=FREEZE_EXCLUDE_NAME,
            using="gist",
        ),
        Index("ix_membership_freezes_membership", "membership_id"),
        {"schema": "memberships"},
    )
    __audited__: ClassVar[bool] = True
    # Sin `__audit_subject__` (no hay `member_id`): pendiente de US-106 (Sprint 4A).

    membership_id: Mapped[UUID] = mapped_column(
        ForeignKey("memberships.memberships.id"), nullable=False
    )
    frozen_from: Mapped[date] = mapped_column(Date, nullable=False)
    frozen_to: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
