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
