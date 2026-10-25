"""Reglas puras de pagos (S3-B3, US-095; D17, S3-D41, S3-D42, S3-D47, S3-D50, S3-D51). Privado
(D7): solo las usa `payments`.

- `validate_paid_at(paid_at, now, *, role, max_retroactive_days)`: exige zona (`PaidAtInvalid`),
  piso `PAID_AT_FLOOR` (`PaidAtInvalid`), techo `now + PAID_AT_FUTURE_TOLERANCE` (`PaidAtInFuture`;
  5 minutos de tolerancia: +4 min 59 s pasa, +5 min 1 s no) y, para todo rol que no sea `admin`,
  `paid_at >= now - max_retroactive_days` (`PaidAtTooRetroactive`, M-8). Compara sin convertir de
  zona: un `paid_at` del año 1 con desfase positivo da 422, nunca `OverflowError`.
- `normalize_reference(value)`: recorta; vacía pasa a `None`; más de 64 caracteres es
  `ValueError` (sin el valor). El patrón de comprobante `REFERENCE_PATTERN` (M-7) lo aplica
  `PaymentIn`.
- `check_balance(agreed_price_cop, paid_cop, amount_cop, *, confirmed)`: saldo = pactado menos lo
  pagado no anulado; un monto mayor al saldo sin confirmar es `PaymentExceedsBalance` (H-1).
- `is_possible_duplicate(recent, candidate, now)`: algún pago no anulado del mismo usuario, monto,
  medio y referencia (o ambas nulas) registrado desde `now - DUPLICATE_WINDOW` (H-1). La ventana
  solo tiene piso: `registered_at` sale del reloj de la base (`created_at`), que puede ir por
  delante del de la aplicación, y un pago "del futuro" cuenta como reciente.
- `check_payment_count(count, *, limit=MAX_PAYMENTS_PER_MEMBERSHIP)`: `count` es cuántos pagos no
  anulados tiene ya la membresía; con `count >= limit` es `PaymentLimitReached` (H-2).
- `can_void(payment)` (S3-B4, D13): verdadero si el pago no está anulado. `void` (B5) la usa con
  la fila bloqueada para responder 409 `payment_already_voided`. No cambia el pago.
- `normalize_void_reason(value)` (S3-B5, US-097; D17, M-7): el motivo de anular un pago, en NFC y
  recortado; vacío, solo espacios, con caracteres de control o invisibles (`Cc`, `Cf`: NUL,
  U+200B) o de más de `VOID_REASON_MAX` (500) caracteres tras recortar es `InvalidVoidReason`
  (422, `field="reason"`, sin el valor en el mensaje). Es la misma regla de `SafeText` más el
  largo: `void` la aplica también cuando no llega por HTTP.
- `is_previous_month(paid_at, today)` (S3-B5, M-8 punto 3, S3-D51): verdadero si el mes civil de
  Bogotá de `paid_at` es anterior al mes de `today` (fecha civil de Bogotá). `void` deja un
  `logger.warning` con solo ids cuando anula un pago así.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from uuid import UUID

from app.core.clock import to_bogota_date
from app.core.validators import check_visible_text
from app.modules.payments.exceptions import (
    InvalidVoidReason,
    PaidAtInFuture,
    PaidAtInvalid,
    PaidAtTooRetroactive,
    PaymentExceedsBalance,
    PaymentLimitReached,
)
from app.modules.payments.models import REFERENCE_MAX_LENGTH, VOID_REASON_MAX_LENGTH, Payment

PAID_AT_FLOOR: Final = datetime(2020, 1, 1, tzinfo=UTC)
PAID_AT_FUTURE_TOLERANCE: Final = timedelta(minutes=5)
DUPLICATE_WINDOW: Final = timedelta(seconds=120)
MAX_PAYMENTS_PER_MEMBERSHIP: Final = 60
REFERENCE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$"
UNLIMITED_ROLE: Final = "admin"
"""El único rol sin tope retroactivo de `paid_at` (M-8); cualquier otro lo tiene."""
VOID_REASON_MAX: Final = VOID_REASON_MAX_LENGTH
"""Largo máximo del motivo de anulación tras recortar (D17; el CHECK de la tabla dice 500)."""


@dataclass(frozen=True, slots=True)
class PaymentFingerprint:
    """Lo que compara la regla de duplicado (H-1): quién, cuánto, cómo, con qué comprobante, si
    está anulado y cuándo se registró (`created_at` de la fila; para el candidato, ahora)."""

    registered_by: UUID
    amount_cop: int
    method: str
    reference: str | None
    voided: bool
    registered_at: datetime


def validate_paid_at(
    paid_at: datetime, now: datetime, *, role: str, max_retroactive_days: int
) -> None:
    """`None` si `paid_at` es válido para el rol; si no, el error de `paid_at` que corresponde."""
    if paid_at.tzinfo is None or paid_at.utcoffset() is None:
        raise PaidAtInvalid()
    if paid_at < PAID_AT_FLOOR:
        raise PaidAtInvalid()
    if paid_at > now + PAID_AT_FUTURE_TOLERANCE:
        raise PaidAtInFuture()
    if role != UNLIMITED_ROLE and paid_at < now - timedelta(days=max_retroactive_days):
        raise PaidAtTooRetroactive()


def normalize_reference(value: str | None) -> str | None:
    """Referencia recortada, `None` si queda vacía; `ValueError` si pasa de 64 caracteres."""
    if value is None:
        return None
    recortada = value.strip()
    if not recortada:
        return None
    if len(recortada) > REFERENCE_MAX_LENGTH:
        raise ValueError("La referencia supera el largo permitido.")
    return recortada


def check_balance(
    agreed_price_cop: int, paid_cop: int, amount_cop: int, *, confirmed: bool
) -> None:
    """`PaymentExceedsBalance` si `amount_cop` supera el saldo y no viene confirmado."""
    saldo = agreed_price_cop - paid_cop
    if amount_cop > saldo and not confirmed:
        raise PaymentExceedsBalance()


def is_possible_duplicate(
    recent: Sequence[PaymentFingerprint], candidate: PaymentFingerprint, now: datetime
) -> bool:
    """Verdadero si algún pago reciente no anulado coincide con el candidato (H-1)."""
    desde = now - DUPLICATE_WINDOW
    return any(
        not previo.voided
        and previo.registered_at >= desde
        and previo.registered_by == candidate.registered_by
        and previo.amount_cop == candidate.amount_cop
        and previo.method == candidate.method
        and previo.reference == candidate.reference
        for previo in recent
    )


def check_payment_count(count: int, *, limit: int = MAX_PAYMENTS_PER_MEMBERSHIP) -> None:
    """`PaymentLimitReached` si la membresía ya tiene `limit` pagos no anulados (H-2)."""
    if count >= limit:
        raise PaymentLimitReached()


def can_void(payment: Payment) -> bool:
    """Verdadero si `payment` todavía se puede anular (no está anulado)."""
    return not payment.voided


def normalize_void_reason(value: str) -> str:
    """El motivo recortado y en NFC; `InvalidVoidReason` si no es válido (S3-B5)."""
    try:
        motivo = check_visible_text(value)
    except ValueError as error:
        raise InvalidVoidReason() from error
    if len(motivo) > VOID_REASON_MAX:
        raise InvalidVoidReason()
    return motivo


def is_previous_month(paid_at: datetime, today: date) -> bool:
    """Verdadero si el mes de Bogotá de `paid_at` es anterior al de `today` (S3-B5)."""
    pagado = to_bogota_date(paid_at)
    return (pagado.year, pagado.month) < (today.year, today.month)
