"""Fachada de membresías (D7): lo único que importan los demás módulos (regla de módulos 1).

- `sell` (S3-B1, US-084; con primer pago desde S3-B4, US-085) y el evento `MembershipSold` (L7:
  se define en `events.py` y se exporta aquí).
- `refs_for` (contrato para `payments`, B8) y `get_payment_target`.
- `freeze` (S3-B2, US-089) y el evento `MembershipFrozen`.
- S3-B4 (D1, D11): `membership_payability` (el gate de pagos), `on_payment_registered` (activa por
  cobertura) y el evento `MembershipActivated`.

Al final del archivo, al importarse (lo hace `main.load_module_services()` en el api, el CLI y
las pruebas): el registro del gate (`payments_service.set_membership_gate`, única llamada del api,
L-5) y la suscripción a `PaymentRegistered`. B5 agrega la de `PaymentVoided`.
"""

from __future__ import annotations

from app.core import events
from app.modules.memberships.events import (
    MembershipActivated,
    MembershipFrozen,
    MembershipSold,
)
from app.modules.memberships.lifecycle import freeze, on_payment_registered
from app.modules.memberships.queries import refs_for
from app.modules.memberships.sell import get_payment_target, membership_payability, sell
from app.modules.payments import service as payments_service

__all__: list[str] = [
    "MembershipActivated",
    "MembershipFrozen",
    "MembershipSold",
    "freeze",
    "get_payment_target",
    "membership_payability",
    "on_payment_registered",
    "refs_for",
    "sell",
]

payments_service.set_membership_gate(membership_payability)
events.subscribe(payments_service.PaymentRegistered, on_payment_registered)
