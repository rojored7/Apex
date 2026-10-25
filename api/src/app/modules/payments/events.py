"""Eventos que emite `payments` (S3-B3; L7: se definen en el emisor y se re-exportan desde
`service.py`). Privado (D7): los suscriptores (`memberships`, B4 y B5) los importan de
`payments.service`.

Solo ids y montos: ningún evento lleva la referencia ni el motivo (S3-D70).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRegistered(DomainEvent):
    """Un pago quedó insertado (y con `flush`) en la transacción (D11)."""

    membership_id: UUID
    payment_id: UUID
    amount_cop: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentVoided(DomainEvent):
    """Un pago quedó anulado en la transacción (lo emite `void`, B5)."""

    membership_id: UUID
    payment_id: UUID
