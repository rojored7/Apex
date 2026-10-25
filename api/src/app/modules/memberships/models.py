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
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, Index, Integer, Text, literal_column, text
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
