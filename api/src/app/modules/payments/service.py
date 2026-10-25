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

`IMMUTABLE_CONSTRAINT` (S3-B4, D13): nombre con que la función `payments.forbid_mutation()` de
`0011_payments_immutability` firma cada rechazo (`CONSTRAINT = payments_immutable`); `void` (B5)
lo compara con `core.db.violated_constraint` para responder 409 `payment_already_voided`.

`void(session, *, payment_id, reason) -> PaymentOut` (S3-B5, US-097; D13, M-8, L-5, S3-D51).
Actor de `get_actor()` (solo admin por la ruta), hora de `current_clock()`. Todo dentro de
`session.begin_nested()`: si un paso o un handler de `PaymentVoided` (la reversión de
`memberships`, US-087) falla, el pago queda sin anular y sin auditoría. Orden de D13 (el mismo de
`register`: membresía, pago):
1. `rules.normalize_void_reason(reason)` (`InvalidVoidReason`, 422 `field="reason"`); sin gate
   `MembershipGateNotRegistered`;
2. leer el pago sin candado (`PaymentNotFound`, 404 `payment_not_found`) para saber su
   `membership_id`;
3. el gate sobre ese `membership_id` (toma `FOR UPDATE` de la membresía). Una membresía
   `cancelled` NO se rechaza: sus pagos se pueden anular y la reversión no la reactiva (L-5);
4. `SELECT ... FOR UPDATE` del pago con `populate_existing`; `rules.can_void` (llamada por el
   módulo `rules`) falso es `PaymentAlreadyVoided` (409);
5. asignar las cuatro columnas de anulación (`voided`, `void_reason`, `voided_by = get_actor()`,
   `voided_at = current_clock().now_utc()`) dentro de esta función (única que las asigna,
   `tests/architecture/test_payments_immutability_code.py`); `flush` (auditoría `update` con el
   socio como sujeto); un `IntegrityError` con `IMMUTABLE_CONSTRAINT` sale como
   `PaymentAlreadyVoided` (`from` el error);
6. si `rules.is_previous_month(paid_at, hoy de Bogotá)`, `logger.warning("void of previous
   month")` del logger `app.payments` con solo `payment_id` y `membership_id` en `extra`;
7. `emit(PaymentVoided)` y la salida con la fila anulada.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.db import violated_constraint
from app.core.events import emit
from app.modules.payments import rules
from app.modules.payments.events import PaymentRegistered, PaymentVoided
from app.modules.payments.exceptions import (
    MembershipCancelled,
    MembershipGateNotRegistered,
    PaymentAlreadyVoided,
    PaymentMembershipNotFound,
    PaymentNotFound,
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

IMMUTABLE_CONSTRAINT: Final = "payments_immutable"
"""`CONSTRAINT` de los rechazos del trigger de `0011` (D13)."""
PREVIOUS_MONTH_WARNING: Final = "void of previous month"
"""Mensaje del aviso al anular un pago de un mes anterior (M-8 punto 3, S3-D51); solo ids."""

logger = logging.getLogger("app.payments")


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


async def void(session: AsyncSession, *, payment_id: UUID, reason: str) -> PaymentOut:
    """Anula el pago con el motivo dado (pasos en el docstring del módulo; S3-B5)."""
    motivo = rules.normalize_void_reason(reason)
    gate = membership_gate()
    if gate is None:
        raise MembershipGateNotRegistered("payments: MembershipGate sin registrar")
    async with session.begin_nested():
        pago = await _lock_for_void(session, gate, payment_id)
        pago.voided = True
        pago.void_reason = motivo
        pago.voided_by = get_actor()
        pago.voided_at = current_clock().now_utc()
        await _flush_void(session)
        _warn_if_previous_month(pago)
        await emit(PaymentVoided(membership_id=pago.membership_id, payment_id=pago.id), session)
    return PaymentOut.model_validate(pago, from_attributes=True)


async def _lock_for_void(session: AsyncSession, gate: MembershipGate, payment_id: UUID) -> Payment:
    """Pasos 2 a 4 de `void` en el orden de D13: el pago sin candado (para su membresía), el gate
    (`FOR UPDATE` de la membresía; una anulada no se rechaza, L-5) y `FOR UPDATE` del pago con
    `populate_existing`. `PaymentNotFound` si no existe; `PaymentAlreadyVoided` si ya está
    anulado (`rules.can_void`, llamada por el módulo)."""
    membership_id = await session.scalar(
        select(Payment.membership_id).where(Payment.id == payment_id)
    )
    if membership_id is None:
        raise PaymentNotFound()
    await gate(session, membership_id)
    consulta = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    pago = (await session.scalars(consulta)).first()
    if pago is None:
        raise PaymentNotFound()
    if not rules.can_void(pago):
        raise PaymentAlreadyVoided()
    return pago


async def _flush_void(session: AsyncSession) -> None:
    """`flush` de la anulación (auditoría `update`); el rechazo del trigger de `0011`
    (`IMMUTABLE_CONSTRAINT`) sale como `PaymentAlreadyVoided` con el error como causa."""
    try:
        await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) == IMMUTABLE_CONSTRAINT:
            raise PaymentAlreadyVoided() from error
        raise


def _warn_if_previous_month(pago: Payment) -> None:
    """Aviso con solo ids si el pago es de un mes civil de Bogotá anterior (M-8, S3-D51)."""
    if rules.is_previous_month(pago.paid_at, current_clock().today_bogota()):
        logger.warning(
            PREVIOUS_MONTH_WARNING,
            extra={"payment_id": pago.id, "membership_id": pago.membership_id},
        )


async def methods(session: AsyncSession) -> PaymentMethodsOut:
    """Los tres medios de pago en orden fijo con sus etiquetas (D24, D25)."""
    medios = await settings_service.payment_methods(session)
    return PaymentMethodsOut(
        items=[PaymentMethodOut(code=m.code, label=m.label, hint=m.hint) for m in medios]
    )


__all__: list[str] = [
    "IMMUTABLE_CONSTRAINT",
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
    "void",
]
