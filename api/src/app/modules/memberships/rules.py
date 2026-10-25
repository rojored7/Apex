"""Reglas puras de membresías (S3-B1, US-083; blueprint, sección 2 "Tipos puros"). Privado (D7).

Sin base, sin reloj y sin E/S: cada función recibe "hoy" (fecha civil de Bogotá) y los datos que
necesita. Los valores son `@dataclass(frozen=True, slots=True)` y validan en `__post_init__`
(`start <= end`, `ValueError`).

- `compute_end_date(start, plan)`: fin inclusivo `start + duration_days` (RN-05, N-23): 30 días
  dan acceso 31 días.
- `compute_status(m, today, expiring_days, freezes)`: estado efectivo en el orden de RN-06
  (cancelada, pendiente de pago, congelada, vencida, por vencer, al día). Solo `cancelled` y
  `pending_payment` salen del estado guardado; el resto se deriva de la fecha (D5).
  `classes_remaining == 0` cuenta como vencida (D15). `ValueError` si `expiring_days < 0`.
- `effective(...)`: el mismo snapshot con el estado de `compute_status`.
- `paid_total`, `covers` (Q5: pagar de más cubre) e `is_covered`.
- `next_start_for_renewal(current, today)`: el día siguiente al fin de la vigente; hoy si no hay
  o si ya venció.
- `classify_open(items, today)`: *vigente* es `active`, `expiring` o `frozen` con
  `start_date <= hoy`; *futura* es `pending_payment` (cualquier fecha) o `active`/`expiring` con
  `start_date > hoy` (D8). Las vencidas y canceladas no cuentan.
- `find_overlap(start, end, others)`: id de la primera con rango cerrado que se cruza.
- `validate_start_date(start, today, *, max_retroactive_days, max_ahead_days)`: N-24 y M-4.

B2 agrega `apply_freeze`, B4 `prefix_field`, B5 `should_revert`, B6 `plan_renewal` y B7
`parse_status_filter` y `resolve_member_status`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.modules.memberships.exceptions import StartDateTooFar, StartDateTooRetroactive

MAX_START_AHEAD_DAYS: Final = 366
"""Una venta empieza a más tardar hoy más 366 días (M-4, S3-D47; `renew` no aplica)."""


class MembershipStatus(StrEnum):
    pending_payment = "pending_payment"
    active = "active"
    expiring = "expiring"
    expired = "expired"
    frozen = "frozen"
    cancelled = "cancelled"


_GUARDADOS_QUE_MANDAN: Final = frozenset(
    {MembershipStatus.cancelled, MembershipStatus.pending_payment}
)
_VIGENTES: Final = frozenset(
    {MembershipStatus.active, MembershipStatus.expiring, MembershipStatus.frozen}
)
_FUTURAS_SI_AUN_NO_EMPIEZAN: Final = frozenset({MembershipStatus.active, MembershipStatus.expiring})


@dataclass(frozen=True, slots=True)
class PlanTerms:
    """Lo que la regla necesita del plan: `kind`, `duration_days` y `class_count`."""

    kind: str
    duration_days: int
    class_count: int | None


@dataclass(frozen=True, slots=True)
class FreezeWindow:
    """Ventana de congelación cerrada `[frozen_from, frozen_to]`."""

    frozen_from: date
    frozen_to: date

    def __post_init__(self) -> None:
        if self.frozen_from > self.frozen_to:
            raise ValueError("frozen_from no puede ser posterior a frozen_to")

    @property
    def days(self) -> int:
        """Días de la ventana, contando los dos extremos (RN-07)."""
        return (self.frozen_to - self.frozen_from).days + 1

    def contains(self, day: date) -> bool:
        return self.frozen_from <= day <= self.frozen_to


@dataclass(frozen=True, slots=True)
class PaymentLine:
    amount_cop: int
    voided: bool


@dataclass(frozen=True, slots=True)
class MembershipSnapshot:
    """Lo que las reglas saben de una membresía (nunca el ORM)."""

    id: UUID
    status: MembershipStatus
    start_date: date
    end_date: date
    classes_remaining: int | None

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date no puede ser posterior a end_date")


@dataclass(frozen=True, slots=True)
class OpenMemberships:
    """Resultado de `classify_open`: la vigente y la futura, si existen."""

    current: MembershipSnapshot | None
    future: MembershipSnapshot | None


def compute_end_date(start_date: date, plan: PlanTerms) -> date:
    """Fin inclusivo `start_date + duration_days` (RN-05, N-23)."""
    return start_date + timedelta(days=plan.duration_days)


def compute_status(
    m: MembershipSnapshot,
    today: date,
    expiring_days: int,
    freezes: Sequence[FreezeWindow],
) -> MembershipStatus:
    """Estado efectivo en el orden de RN-06 (D5): cancelada y pendiente de pago se leen de lo
    guardado; congelada si una ventana contiene hoy; vencida si hoy pasó el fin o no quedan
    clases; por vencer si faltan `expiring_days` días o menos; si no, al día."""
    if expiring_days < 0:
        raise ValueError("expiring_days no puede ser negativo")
    if m.status in _GUARDADOS_QUE_MANDAN:
        return m.status
    if any(ventana.contains(today) for ventana in freezes):
        return MembershipStatus.frozen
    if today > m.end_date or m.classes_remaining == 0:
        return MembershipStatus.expired
    if (m.end_date - today).days <= expiring_days:
        return MembershipStatus.expiring
    return MembershipStatus.active


def effective(
    m: MembershipSnapshot,
    today: date,
    expiring_days: int,
    freezes: Sequence[FreezeWindow],
) -> MembershipSnapshot:
    """Una copia de `m` con el estado de `compute_status` (no muta `m`)."""
    return replace(m, status=compute_status(m, today, expiring_days, freezes))


def paid_total(lines: Iterable[PaymentLine]) -> int:
    """Suma de los pagos no anulados."""
    return sum(linea.amount_cop for linea in lines if not linea.voided)


def covers(agreed_price_cop: int, paid_cop: int) -> bool:
    """Lo pagado cubre el precio pactado; pagar de más también cubre (Q5)."""
    return paid_cop >= agreed_price_cop


def is_covered(agreed_price_cop: int, lines: Iterable[PaymentLine]) -> bool:
    """`covers` sobre la suma de los no anulados; sin pagos no cubre (el precio es > 0)."""
    return covers(agreed_price_cop, paid_total(lines))


def next_start_for_renewal(current: MembershipSnapshot | None, today: date) -> date:
    """El día siguiente al fin de la vigente; hoy si no hay o si ya venció (Q1)."""
    if current is None or current.end_date < today:
        return today
    return current.end_date + timedelta(days=1)


def _es_futura(m: MembershipSnapshot, today: date) -> bool:
    if m.status == MembershipStatus.pending_payment:
        return True
    return m.status in _FUTURAS_SI_AUN_NO_EMPIEZAN and m.start_date > today


def classify_open(items: Iterable[MembershipSnapshot], today: date) -> OpenMemberships:
    """La primera vigente y la primera futura (D8), sobre snapshots con estado efectivo; las
    vencidas y las canceladas no cuentan."""
    actual: MembershipSnapshot | None = None
    futura: MembershipSnapshot | None = None
    for m in items:
        if _es_futura(m, today):
            futura = futura or m
        elif m.status in _VIGENTES and m.start_date <= today:
            actual = actual or m
    return OpenMemberships(current=actual, future=futura)


def find_overlap(start: date, end: date, others: Iterable[MembershipSnapshot]) -> UUID | None:
    """Id de la primera de `others` cuyo rango cerrado se cruza con `[start, end]` (el mismo día
    choca; el día siguiente no, como `daterange(start, end, '[]')`)."""
    for m in others:
        if m.start_date <= end and start <= m.end_date:
            return m.id
    return None


def validate_start_date(
    start: date,
    today: date,
    *,
    max_retroactive_days: int | None,
    max_ahead_days: int = MAX_START_AHEAD_DAYS,
) -> None:
    """`StartDateTooRetroactive` antes de `today - max_retroactive_days` (`None` = sin tope, la
    importación de N-24) y `StartDateTooFar` después de `today + max_ahead_days`. Nunca
    `OverflowError`: resta fechas (siempre representable) y no suma días a `start`."""
    if (start - today).days > max_ahead_days:
        raise StartDateTooFar()
    if max_retroactive_days is not None and (today - start).days > max_retroactive_days:
        raise StartDateTooRetroactive()
