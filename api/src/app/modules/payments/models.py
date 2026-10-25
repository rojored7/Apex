"""Tabla `payments.payments` (S3-B3, US-095; migración `0010_payments`; D17, D24, S3-D41).

- Un pago es inmutable (regla de datos 5): nunca `UPDATE` ni `DELETE`; un error se corrige con
  `voided = true`, `void_reason`, `voided_by` y `voided_at` (B5) y un pago nuevo. Los triggers que
  lo imponen en la base llegan con `0011_payments_immutability` (B4).
- `membership_id` y `member_id` sin FK (otro esquema, regla de módulos 2). `member_id` es la copia
  del socio de la membresía que da el gate (D1): no cambia nunca y sirve de sujeto de auditoría.
- `amount_cop` entero COP entre 1 y `MAX_AMOUNT_COP` (D17); `method` uno de `PAYMENT_METHODS`
  (D24: los mismos códigos de `settings.schemas.PAYMENT_METHOD_CODES`, del `Literal` de
  `payments.schemas` y del CHECK de la migración); `reference` de 1 a 64 caracteres o nula;
  `paid_at` con zona; `registered_by` es el actor que registró.
- CHECKs con nombre (la convención les antepone `ck_payments_`): `amount_range`, `method`,
  `reference_length`, `void_reason_length` y `void_coherent` (las cuatro columnas de anulación van
  juntas: todas nulas sin anular, todas llenas y con motivo visible al anular).
- Índices `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id` e
  `ix_payments_member_paid (member_id, paid_at DESC)`.
- `__audited__` con `__audit_subject__ = "member_id"` (G-05): la fila de auditoría lleva el socio.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

PAYMENT_METHODS: Final[tuple[str, ...]] = ("cash", "nequi", "breb")
MAX_AMOUNT_COP: Final[int] = 1_000_000_000
REFERENCE_MAX_LENGTH: Final[int] = 64
VOID_REASON_MAX_LENGTH: Final[int] = 500


class Payment(CommonColumnsMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_cop BETWEEN 1 AND 1000000000", name="amount_range"),
        CheckConstraint("method IN ('cash', 'nequi', 'breb')", name="method"),
        CheckConstraint(
            "reference IS NULL OR char_length(reference) BETWEEN 1 AND 64",
            name="reference_length",
        ),
        CheckConstraint(
            "void_reason IS NULL OR char_length(void_reason) <= 500", name="void_reason_length"
        ),
        CheckConstraint(
            "(voided = false AND void_reason IS NULL AND voided_by IS NULL AND voided_at IS NULL) "
            "OR (voided = true AND void_reason IS NOT NULL AND btrim(void_reason) <> '' "
            "AND voided_by IS NOT NULL AND voided_at IS NOT NULL)",
            name="void_coherent",
        ),
        Index("ix_payments_paid_at", text("paid_at DESC")),
        Index("ix_payments_membership_id", "membership_id"),
        Index("ix_payments_member_paid", "member_id", text("paid_at DESC")),
        {"schema": "payments"},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    membership_id: Mapped[UUID] = mapped_column(nullable=False)
    member_id: Mapped[UUID] = mapped_column(nullable=False)
    amount_cop: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime] = mapped_column(nullable=False)
    registered_by: Mapped[UUID] = mapped_column(nullable=False)
    voided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_by: Mapped[UUID | None] = mapped_column(nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(nullable=True)
