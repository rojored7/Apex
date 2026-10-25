"""Fachada de membresías (D7): lo único que importan los demás módulos (regla de módulos 1).

- `sell` (S3-B1, US-084) y el evento `MembershipSold` (L7: se define en `events.py` y se exporta
  aquí).
- `refs_for` (contrato para `payments`, B8) y `get_payment_target` (gate de pagos, B4).
- `freeze` (S3-B2, US-089) y el evento `MembershipFrozen`.

B4 agrega al final del archivo el registro del gate (`payments_service.set_membership_gate`) y
las suscripciones a `PaymentRegistered` y `PaymentVoided`.
"""

from __future__ import annotations

from app.modules.memberships.events import MembershipFrozen, MembershipSold
from app.modules.memberships.lifecycle import freeze
from app.modules.memberships.queries import refs_for
from app.modules.memberships.sell import get_payment_target, sell

__all__: list[str] = [
    "MembershipFrozen",
    "MembershipSold",
    "freeze",
    "get_payment_target",
    "refs_for",
    "sell",
]
