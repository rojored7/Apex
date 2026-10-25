"""Fachada de membresías (D7): lo único que importan los demás módulos (regla de módulos 1).

- `sell` (S3-B1, US-084; con primer pago desde S3-B4, US-085) y el evento `MembershipSold` (L7:
  se define en `events.py` y se exporta aquí).
- `refs_for` (contrato para `payments`, B8).
- `freeze` (S3-B2, US-089) y el evento `MembershipFrozen`.
- S3-B4 (D1, D11): `membership_payability` (el gate de pagos), `on_payment_registered` (activa por
  cobertura) y el evento `MembershipActivated`.
- S3-B5 (D13, US-087): `on_payment_voided` (revierte a `pending_payment` la que deja de estar
  cubierta) y el evento `MembershipActivationReverted`.
- S3-B6 (US-088, US-090): `renewal_preview` (la renovación es `sell(..., renew=True)`), `cancel`
  y el evento `MembershipCancelled`.

- S3-B7 (US-091, US-092): `list`, `get`, `summary`, `status_for`, `member_ids_by_status`,
  `count_active_by_plan` (contratos para `members`, `plans` y `dashboard`) y el tipo
  `MemberMembership`. `list` sombrea al `list` de Python: aquí se usa `builtins.list`.
- S3-B11 (US-093, D28): `list_for_member` (la pestaña de membresías de la ficha).

Al final del archivo, al importarse (lo hace `main.load_module_services()` en el api, el CLI y
las pruebas): el registro del gate (`payments_service.set_membership_gate`, única llamada del api,
L-5), las suscripciones a `PaymentRegistered` y `PaymentVoided` (B5) y, desde S3-B7 (S3-D53,
E11), la de `summary._mark_summary_dirty` (en `summary.py` desde S3-D90) a los eventos que
cambian el resumen (después de los handlers de negocio).
"""

from __future__ import annotations

import builtins

from app.core import events
from app.modules.members import service as members_service
from app.modules.memberships import summary as summary_cache
from app.modules.memberships.events import (
    MembershipActivated,
    MembershipActivationReverted,
    MembershipCancelled,
    MembershipFrozen,
    MembershipSold,
)
from app.modules.memberships.lifecycle import (
    cancel,
    freeze,
    on_payment_registered,
    on_payment_voided,
)
from app.modules.memberships.queries import (
    count_active_by_plan,
    get,
    list,
    list_for_member,
    member_ids_by_status,
    refs_for,
    status_for,
)
from app.modules.memberships.schemas import MemberMembership
from app.modules.memberships.sell import (
    membership_payability,
    renewal_preview,
    sell,
)
from app.modules.memberships.summary import summary
from app.modules.payments import service as payments_service

__all__: builtins.list[str] = [
    "MemberMembership",
    "MembershipActivated",
    "MembershipActivationReverted",
    "MembershipCancelled",
    "MembershipFrozen",
    "MembershipSold",
    "cancel",
    "count_active_by_plan",
    "freeze",
    "get",
    "list",
    "list_for_member",
    "member_ids_by_status",
    "membership_payability",
    "on_payment_registered",
    "on_payment_voided",
    "refs_for",
    "renewal_preview",
    "sell",
    "status_for",
    "summary",
]

payments_service.set_membership_gate(membership_payability)
events.subscribe(payments_service.PaymentRegistered, on_payment_registered)
events.subscribe(payments_service.PaymentVoided, on_payment_voided)

# S3-B7 (S3-D53, E11): el resumen cambia con estos eventos; el handler solo marca la sesión.
for _evento in (
    MembershipSold,
    MembershipActivated,
    MembershipActivationReverted,
    MembershipFrozen,
    MembershipCancelled,
    payments_service.PaymentRegistered,
    payments_service.PaymentVoided,
    # Fase 4 del Sprint 3 (M1, PM1; S3-D89; cierra B7 LOW-1): el resumen solo cuenta socios no
    # dados de baja, así que la baja y la reactivación también lo cambian.
    members_service.MemberDeactivated,
    members_service.MemberReactivated,
):
    events.subscribe(_evento, summary_cache._mark_summary_dirty)
