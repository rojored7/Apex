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

S3-B8 (US-098, US-099, US-100; D23, D26, M-4, M-8, L-2, S3-D47, S3-D51, S3-D57):
- `PaymentFilters` y `build_filters(filters, member_ids_from_q)`: las condiciones de la lista
  (`[from_, to)`, medio, quién registró, `voided` y `backdated` tri-estado, socio, membresía y
  `q` como `lower(reference) = lower(q)` o `member_id` en los ids de la búsqueda de socios).
- `check_date_range(from_, to, today)`: `from` y `to` entre `DATE_FLOOR` y `date_ceiling(today)`
  (hoy más `DATE_CEILING_YEARS`), no invertidas; si no, `InvalidDateRange` con el campo.
- `parse_month(value)` y `month_bounds_utc(month)`: `AAAA-MM` con año de `MONTH_MIN` a
  `MONTH_MAX`; el rango `[inicio, fin)` en UTC del mes civil de Bogotá, con aritmética de
  `(año, mes)` (nunca `datetime(año + 1, ...)` sin guardia); si no, `InvalidMonth`.
- `partial_email(email)`: primera letra, `•••` y `@dominio` (`registered_by_name`,
  `voided_by_name`).
- `is_backdated(paid_at, created_at)`: registrado más de `BACKDATED_AFTER` después del pago.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_

from app.core.clock import BOGOTA, to_bogota_date
from app.core.pagination import any_uuids
from app.core.validators import check_visible_text
from app.modules.payments.exceptions import (
    InvalidDateRange,
    InvalidMonth,
    InvalidVoidReason,
    PaidAtInFuture,
    PaidAtInvalid,
    PaidAtTooRetroactive,
    PaymentExceedsBalance,
    PaymentLimitReached,
)
from app.modules.payments.models import REFERENCE_MAX_LENGTH, VOID_REASON_MAX_LENGTH, Payment

if TYPE_CHECKING:  # solo el tipo (PM5 de Fase 4): las reglas no cargan `core.security`
    from app.core.security import Role

PAID_AT_FLOOR: Final = datetime(2020, 1, 1, tzinfo=UTC)
PAID_AT_FUTURE_TOLERANCE: Final = timedelta(minutes=5)
DUPLICATE_WINDOW: Final = timedelta(seconds=120)
MAX_PAYMENTS_PER_MEMBERSHIP: Final = 60
REFERENCE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$"
UNLIMITED_ROLE: Final[Role] = "admin"
"""El único rol sin tope retroactivo de `paid_at` (M-8); cualquier otro, o ninguno (`None`, un
llamador interno sin rol, S3-D81), lo tiene."""
VOID_REASON_MAX: Final = VOID_REASON_MAX_LENGTH
"""Largo máximo del motivo de anulación tras recortar (D17; el CHECK de la tabla dice 500)."""
DATE_FLOOR: Final = PAID_AT_FLOOR
"""Piso de `from` y `to` de la lista (M-4, S3-D47): el mismo de `paid_at`."""
DATE_CEILING_YEARS: Final = 5
"""`from` y `to` hasta hoy más 5 años (M-4, S3-D47)."""
MONTH_MIN: Final = 2020
MONTH_MAX: Final = 2100
MONTH_LENGTH: Final = 7
"""`AAAA-MM`: el largo máximo que acepta el parámetro `month` antes de `parse_month`."""
BACKDATED_AFTER: Final = timedelta(hours=24)
"""Un pago es `backdated` si se registró más de 24 h después de `paid_at` (M-8, S3-D51)."""
EMAIL_MASK: Final = chr(0x2022) * 3
"""Lo que reemplaza la parte local del correo salvo su primera letra (L-2, S3-D57)."""
_MONTH_RE: Final = re.compile(r"([0-9]{4})-([0-9]{2})")


@dataclass(frozen=True, slots=True)
class PaymentFilters:
    """Filtros de `GET /payments` ya validados (S3-B8, D26, S3-D51). `from_` y `to` forman el
    rango `[from_, to)`; `voided` y `backdated` son tri-estado (`None` no filtra); `q` compara
    la referencia completa sin mayúsculas o el socio por los ids de `members.search_ids`."""

    q: str | None = None
    from_: datetime | None = None
    to: datetime | None = None
    method: str | None = None
    registered_by: UUID | None = None
    voided: bool | None = None
    backdated: bool | None = None
    member_id: UUID | None = None
    membership_id: UUID | None = None


def build_filters(
    filters: PaymentFilters, member_ids_from_q: Collection[UUID] = ()
) -> list[ColumnElement[bool]]:
    """Las condiciones de `filters` sobre `Payment` (vacía sin filtros). El rango es
    `[from_, to)`; `q` en blanco no filtra y sin `q` los ids de la búsqueda no cuentan."""
    condiciones: list[ColumnElement[bool]] = []
    if filters.from_ is not None:
        condiciones.append(Payment.paid_at >= filters.from_)
    if filters.to is not None:
        condiciones.append(Payment.paid_at < filters.to)
    for columna, valor in (
        (Payment.method, filters.method),
        (Payment.registered_by, filters.registered_by),
        (Payment.voided, filters.voided),
        (Payment.member_id, filters.member_id),
        (Payment.membership_id, filters.membership_id),
    ):
        if valor is not None:
            condiciones.append(columna == valor)
    if filters.backdated is not None:
        demora = Payment.created_at - Payment.paid_at
        condiciones.append(
            demora > BACKDATED_AFTER if filters.backdated else demora <= BACKDATED_AFTER
        )
    if filters.q is not None and filters.q.strip():
        condiciones.append(_q_condition(filters.q.strip(), member_ids_from_q))
    return condiciones


def _q_condition(q: str, member_ids: Collection[UUID]) -> ColumnElement[bool]:
    """`lower(reference) = lower(q)` (exacta) o el socio entre los ids de la búsqueda, como un
    solo parámetro `uuid[]` (`= ANY(:ids)`, S3-D60)."""
    referencia = func.lower(Payment.reference) == q.lower()
    if not member_ids:
        return referencia
    socios = Payment.member_id == any_uuids(member_ids)
    return or_(referencia, socios)


def date_ceiling(today: date) -> datetime:
    """Techo de `from` y `to` con zona: el inicio (UTC) del mismo día `DATE_CEILING_YEARS` años
    después; un 29 de febrero pasa al 28."""
    anio = today.year + DATE_CEILING_YEARS
    dia = 28 if (today.month, today.day) == (2, 29) else today.day
    return datetime(anio, today.month, dia, tzinfo=UTC)


def _outside(value: datetime, ceiling: datetime) -> bool:
    """Fuera de `[DATE_FLOOR, ceiling]`. El año se mira primero: comparar un año 1 o 9999 con
    desfase podría desbordar al pasar a UTC (M-4)."""
    if value.year < DATE_FLOOR.year - 1 or value.year > ceiling.year + 1:
        return True
    return value < DATE_FLOOR or value > ceiling


def check_date_range(from_: datetime | None, to: datetime | None, today: date) -> None:
    """`InvalidDateRange` con el campo que falla (`from`, `to`; invertidas, `to`)."""
    techo = date_ceiling(today)
    if from_ is not None and _outside(from_, techo):
        raise InvalidDateRange(field="from")
    if to is not None and _outside(to, techo):
        raise InvalidDateRange(field="to")
    if from_ is not None and to is not None and to < from_:
        raise InvalidDateRange(field="to")


def parse_month(value: str) -> tuple[int, int]:
    """`(año, mes)` de `AAAA-MM` con dígitos ASCII (`fullmatch`: sin espacios ni salto de línea
    final), mes de 1 a 12 y año de `MONTH_MIN` a `MONTH_MAX`; si no, `InvalidMonth`."""
    coincide = _MONTH_RE.fullmatch(value)
    if coincide is None:
        raise InvalidMonth()
    anio, mes = int(coincide.group(1)), int(coincide.group(2))
    if not (MONTH_MIN <= anio <= MONTH_MAX and 1 <= mes <= 12):
        raise InvalidMonth()
    return anio, mes


def month_bounds_utc(month: str) -> tuple[datetime, datetime]:
    """`[inicio, fin)` en UTC del mes civil de Bogotá `AAAA-MM`, con aritmética de `(año, mes)`:
    diciembre pasa a enero del año siguiente (`2100-12` termina en 2101-01-01T05:00Z)."""
    anio, mes = parse_month(month)
    siguiente = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    inicio = datetime(anio, mes, 1, tzinfo=BOGOTA).astimezone(UTC)
    fin = datetime(siguiente[0], siguiente[1], 1, tzinfo=BOGOTA).astimezone(UTC)
    return inicio, fin


def partial_email(email: str) -> str:
    """Primera letra de la parte local, `•••` y `@dominio` tras la última `@` (L-2, S3-D57);
    sin `@`, primera letra y `•••`; vacío, `•••`. Nunca más de una letra de la parte local."""
    local, arroba, dominio = email.rpartition("@")
    if not arroba:
        return email[:1] + EMAIL_MASK
    return f"{local[:1]}{EMAIL_MASK}@{dominio}"


def is_backdated(paid_at: datetime, created_at: datetime) -> bool:
    """Verdadero si `created_at - paid_at > BACKDATED_AFTER` (M-8, S3-D51): 24 h exactas no."""
    return created_at - paid_at > BACKDATED_AFTER


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
    paid_at: datetime, now: datetime, *, role: Role | None, max_retroactive_days: int
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
