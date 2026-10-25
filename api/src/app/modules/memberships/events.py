"""Eventos que emite `memberships` (S3-B1; L7: se definen en el emisor y se re-exportan desde
`service.py`). Privado (D7): los suscriptores los importan de `memberships.service`.

Solo ids, fechas y montos: ningún evento lleva datos personales (S3-D70).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipSold(DomainEvent):
    """Una venta (o renovación, `renewal=True`, B6) quedó insertada en la transacción."""

    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    agreed_price_cop: int
    start_date: date
    end_date: date
    renewal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipFrozen(DomainEvent):
    """Una congelación quedó insertada y el fin de la membresía corrido (S3-B2, D14)."""

    membership_id: UUID
    member_id: UUID
    frozen_from: date
    frozen_to: date
    days: int
    end_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipActivated(DomainEvent):
    """Una `pending_payment` quedó cubierta por sus pagos no anulados y pasó al estado efectivo
    (`active`, `expiring`, `frozen` o `expired`; S3-B4, D11). Lo emite `on_payment_registered`."""

    membership_id: UUID
    member_id: UUID
    status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipActivationReverted(DomainEvent):
    """Una membresía `active`, `expiring` o `frozen` (estado efectivo) dejó de estar cubierta al
    anularse un pago y volvió a `pending_payment`, conservando congelaciones y `end_date` (S3-B5,
    US-087, D13, N-25). `previous_status` es el estado efectivo antes de revertir. Lo emite
    `on_payment_voided`."""

    membership_id: UUID
    member_id: UUID
    previous_status: str
