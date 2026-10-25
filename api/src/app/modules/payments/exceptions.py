"""Errores de dominio de pagos (S3-B3, US-095; D34, S3-D41, S3-D42, S3-D47, S3-D51).

Ningún `message` repite valores del usuario (monto, referencia, fechas). Todos conservan la firma
de `DomainError` (`code`, `message`, `field`, `existing_id`, `status`): `memberships.sell` los
re-lanza con el `field` prefijado (`first_payment.amount_cop`, B4, E5).

`MembershipGateNotRegistered` NO es un error de dominio: es un `RuntimeError` (falla cerrado,
sale como 500 sin datos) cuando nadie registró el puerto `MembershipGate` (D1).
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class PaymentError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "payment_error"
    default_message = "La operación sobre el pago no es válida."


class PaymentMembershipNotFound(PaymentError):
    """El gate dice que la membresía no existe."""

    status = 404
    code = "membership_not_found"
    default_message = "No se encontró la membresía."


class MembershipCancelled(PaymentError):
    """La membresía está anulada: no recibe pagos (las vencidas y congeladas sí, N-28)."""

    status = 409
    code = "membership_cancelled"
    default_message = "La membresía está anulada y no recibe pagos."


class _PaidAtError(PaymentError):
    """Base de los errores de `paid_at`: 422 con `field="paid_at"` por defecto."""

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "paid_at",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class PaidAtInvalid(_PaidAtError):
    """`paid_at` sin zona horaria o anterior a `rules.PAID_AT_FLOOR` (M-4, S3-D47)."""

    status = 422
    code = "validation_error"
    default_message = "La fecha del pago no es válida."


class PaidAtInFuture(PaidAtInvalid):
    """`paid_at` más allá de ahora más `rules.PAID_AT_FUTURE_TOLERANCE`."""

    default_message = "La fecha del pago no puede estar en el futuro."


class PaidAtTooRetroactive(_PaidAtError):
    """Un coach registra con `paid_at` anterior a ahora menos `max_retroactive_days` (M-8,
    S3-D51); el admin no tiene ese tope (solo el piso)."""

    status = 422
    code = "paid_at_too_retroactive"
    default_message = "La fecha del pago es demasiado antigua para tu rol."


class PaymentExceedsBalance(PaymentError):
    """El monto supera el saldo de la membresía y no vino `confirm_overpayment` (H-1, S3-D41)."""

    status = 409
    code = "payment_exceeds_balance"
    default_message = "El monto supera el saldo de la membresía. Confirma para registrarlo."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "amount_cop",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class PossibleDuplicatePayment(PaymentError):
    """Hay un pago igual del mismo usuario en los últimos 120 s y no vino `confirm_duplicate`
    (H-1, S3-D41)."""

    status = 409
    code = "payment_possible_duplicate"
    default_message = "Ya registraste un pago igual hace menos de 2 minutos. Confirma si es otro."


class PaymentLimitReached(PaymentError):
    """La membresía ya tiene `rules.MAX_PAYMENTS_PER_MEMBERSHIP` pagos no anulados (H-2)."""

    status = 409
    code = "payment_limit_reached"
    default_message = "La membresía alcanzó el máximo de pagos registrados."


class PaymentNotFound(PaymentError):
    """El pago no existe (B5 y B8)."""

    status = 404
    code = "payment_not_found"
    default_message = "No se encontró el pago."


class MembershipGateNotRegistered(RuntimeError):
    """Nadie registró el puerto `MembershipGate` (D1): `register` y `void` fallan cerrados."""
