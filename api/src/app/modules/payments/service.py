"""Fachada de pagos (D7): lo único que importan los demás módulos (regla de módulos 1).

Puerto `MembershipGate` (D1, G-03): `payments` no importa `memberships` a nivel de módulo. El dueño
de las membresías registra al cargarse (B4, al final de `memberships/service.py`) un adaptador que
toma `SELECT ... FOR UPDATE` de la fila de la membresía y devuelve `MembershipPayability`
(`exists`, `cancelled`, `member_id`, `agreed_price_cop`; S3-C21). Sin gate, `register` (y `void`,
B5) lanzan `MembershipGateNotRegistered`: fallan cerrados y no escriben nada. Las pruebas usan el
doble opt-in `gate_doble` de `tests/payments/conftest.py`.

`register(session, *, membership_id, amount_cop, method, reference=None, paid_at=None,
confirm_overpayment=False, confirm_duplicate=False, role) -> PaymentOut` (US-095; D3, D11, H-1,
H-2, M-4, M-8). Actor de `get_actor()`, hora de `current_clock()`. Todo dentro de
`session.begin_nested()` (como `sell`): si un paso o un handler de `PaymentRegistered` falla, no
queda pago ni auditoría.
1. Gate (toma la fila de la membresía; es el candado que serializa los pagos de una membresía):
   sin gate `MembershipGateNotRegistered`; `exists` falso `PaymentMembershipNotFound` (404);
   `cancelled` `MembershipCancelled` (409). Las vencidas y congeladas reciben pagos (N-28).
2. `paid_at` por defecto `current_clock().now_utc()`; `rules.validate_paid_at(..., role=role,
   max_retroactive_days=settings.memberships_policy(session).max_retroactive_days)`.
3. Bajo el candado del gate: `sum_not_voided` y `rules.check_balance` con `confirm_overpayment`;
   `count_not_voided` y `rules.check_payment_count`; `_recent_fingerprints` desde
   `now - DUPLICATE_WINDOW` y `rules.is_possible_duplicate`, salvo `confirm_duplicate`.
4. `Payment(member_id=gate.member_id, registered_by=get_actor(), ...)`, `flush` (el hook audita con
   el socio como sujeto; `eager_defaults` trae `created_at`) y solo entonces
   `emit(PaymentRegistered)`.

`sum_not_voided`, `sums_not_voided` (de `queries.py`) y `methods(session) -> PaymentMethodsOut`
(los tres medios en orden fijo con las etiquetas de `settings.service.payment_methods`, D24, D25).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.events import emit
from app.modules.payments import rules
from app.modules.payments.events import PaymentRegistered, PaymentVoided
from app.modules.payments.exceptions import (
    MembershipCancelled,
    MembershipGateNotRegistered,
    PaymentMembershipNotFound,
    PossibleDuplicatePayment,
)
from app.modules.payments.models import Payment
from app.modules.payments.queries import (
    _recent_fingerprints,
    count_not_voided,
    sum_not_voided,
    sums_not_voided,
)
from app.modules.payments.schemas import PaymentMethodOut, PaymentMethodsOut, PaymentOut
from app.modules.settings import service as settings_service


@dataclass(frozen=True, slots=True)
class MembershipPayability:
    """Lo que el gate sabe de la membresía, leída con la fila bloqueada (D1, S3-D41)."""

    exists: bool
    cancelled: bool
    member_id: UUID | None
    agreed_price_cop: int | None


MembershipGate = Callable[[AsyncSession, UUID], Awaitable[MembershipPayability]]

_gate: MembershipGate | None = None


def set_membership_gate(gate: MembershipGate | None) -> None:
    """Registra (o quita, con `None`) el puerto; solo lo llama `memberships/service.py` (B4)."""
    global _gate
    _gate = gate


def membership_gate() -> MembershipGate | None:
    """El gate registrado, o `None`."""
    return _gate


async def register(
    session: AsyncSession,
    *,
    membership_id: UUID,
    amount_cop: int,
    method: str,
    reference: str | None = None,
    paid_at: datetime | None = None,
    confirm_overpayment: bool = False,
    confirm_duplicate: bool = False,
    role: str,
) -> PaymentOut:
    """Registra un pago de la membresía (pasos en el docstring del módulo)."""
    gate = membership_gate()
    if gate is None:
        raise MembershipGateNotRegistered("payments: MembershipGate sin registrar")
    async with session.begin_nested():
        membresia = await _payable(session, gate, membership_id)
        ahora = current_clock().now_utc()
        fecha = ahora if paid_at is None else paid_at
        politica = await settings_service.memberships_policy(session)
        rules.validate_paid_at(
            fecha, ahora, role=role, max_retroactive_days=politica.max_retroactive_days
        )
        candidato = rules.PaymentFingerprint(
            registered_by=get_actor(),
            amount_cop=amount_cop,
            method=method,
            reference=reference,
            voided=False,
            registered_at=ahora,
        )
        await _check_under_lock(
            session,
            membresia,
            candidato,
            confirm_overpayment=confirm_overpayment,
            confirm_duplicate=confirm_duplicate,
        )
        pago = await _insert_payment(session, membresia, candidato, fecha)
    return PaymentOut.model_validate(pago, from_attributes=True)


@dataclass(frozen=True, slots=True)
class _Payable:
    """La membresía ya bloqueada por el gate, con lo que el registro necesita."""

    membership_id: UUID
    member_id: UUID
    agreed_price_cop: int


async def _payable(session: AsyncSession, gate: MembershipGate, membership_id: UUID) -> _Payable:
    """Llama al gate una vez (toma el candado de la fila) y traduce su respuesta a 404 o 409."""
    estado = await gate(session, membership_id)
    if not estado.exists or estado.member_id is None or estado.agreed_price_cop is None:
        raise PaymentMembershipNotFound()
    if estado.cancelled:
        raise MembershipCancelled()
    return _Payable(membership_id, estado.member_id, estado.agreed_price_cop)


async def _check_under_lock(
    session: AsyncSession,
    membresia: _Payable,
    candidato: rules.PaymentFingerprint,
    *,
    confirm_overpayment: bool,
    confirm_duplicate: bool,
) -> None:
    """Saldo (H-1), tope de pagos (H-2) y posible duplicado (H-1), con la fila bloqueada."""
    pagado = await sum_not_voided(session, membresia.membership_id)
    rules.check_balance(
        membresia.agreed_price_cop, pagado, candidato.amount_cop, confirmed=confirm_overpayment
    )
    rules.check_payment_count(await count_not_voided(session, membresia.membership_id))
    if confirm_duplicate:
        return
    desde = candidato.registered_at - rules.DUPLICATE_WINDOW
    recientes = await _recent_fingerprints(session, membresia.membership_id, desde)
    if rules.is_possible_duplicate(recientes, candidato, candidato.registered_at):
        raise PossibleDuplicatePayment()


async def _insert_payment(
    session: AsyncSession,
    membresia: _Payable,
    candidato: rules.PaymentFingerprint,
    paid_at: datetime,
) -> Payment:
    """Inserta el pago con el socio del gate, hace `flush` (auditoría) y emite el evento."""
    pago = Payment(
        membership_id=membresia.membership_id,
        member_id=membresia.member_id,
        amount_cop=candidato.amount_cop,
        method=candidato.method,
        reference=candidato.reference,
        paid_at=paid_at,
        registered_by=candidato.registered_by,
    )
    session.add(pago)
    await session.flush()
    evento = PaymentRegistered(
        membership_id=pago.membership_id, payment_id=pago.id, amount_cop=pago.amount_cop
    )
    await emit(evento, session)
    return pago


async def methods(session: AsyncSession) -> PaymentMethodsOut:
    """Los tres medios de pago en orden fijo con sus etiquetas (D24, D25)."""
    medios = await settings_service.payment_methods(session)
    return PaymentMethodsOut(
        items=[PaymentMethodOut(code=m.code, label=m.label, hint=m.hint) for m in medios]
    )


__all__: list[str] = [
    "MembershipGate",
    "MembershipGateNotRegistered",
    "MembershipPayability",
    "PaymentRegistered",
    "PaymentVoided",
    "membership_gate",
    "methods",
    "register",
    "set_membership_gate",
    "sum_not_voided",
    "sums_not_voided",
]
