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
- `snapshot(fuente)` (PM4 de la revisión de Fase 4 del Sprint 3): el `MembershipSnapshot` de
  cualquier objeto con `id`, `status` (texto guardado), `start_date`, `end_date` y
  `classes_remaining` (la fila del ORM o una fila de columnas de un `select`); `ValueError` si
  el estado no existe. Es el único constructor del snapshot.
- `paid_total`, `covers` (Q5: pagar de más cubre) e `is_covered`.
- `next_start_for_renewal(current, today)`: el día siguiente al fin de la vigente; hoy si no hay
  o si ya venció.
- `classify_open(items, today)`: *vigente* es `active`, `expiring` o `frozen` con
  `start_date <= hoy`; *futura* es `pending_payment` (cualquier fecha) o `active`/`expiring` con
  `start_date > hoy` (D8). Las vencidas y canceladas no cuentan.
- `find_overlap(start, end, others)`: id de la primera con rango cerrado que se cruza.
- `validate_start_date(start, today, *, max_retroactive_days, max_ahead_days)`: N-24 y M-4.
- `apply_freeze(m, freezes, frozen_from, frozen_to, limits, today, expiring_days)` (S3-B2, D14,
  Q9): `FreezeOutcome(window, new_end_date)` o `FreezeError(code, field, status)`. Valida en este
  orden: estado efectivo `active` o `expiring` (409 `membership_not_freezable`); fechas invertidas
  (422 `validation_error`, `field="frozen_to"`); `frozen_from` antes de hoy menos
  `max_retroactive_days` (422 `freeze_too_retroactive`, `field="frozen_from"`); `frozen_from`
  fuera de `[start_date, end_date]` (422 `freeze_outside_validity`, `field="frozen_from"`); una
  ventana con `frozen_to >= today` (409 `freeze_already_scheduled`); `max_count` ventanas ya
  usadas (409 `freeze_limit_reached`); días usados más los nuevos sobre `max_days` (409
  `freeze_days_exceeded`). Cuenta los días restando fechas antes de sumar al fin: un
  `frozen_to` enorme da `freeze_days_exceeded` y nunca `OverflowError`. El fin se corre los días
  de la ventana también si es futura (RN-07). No muta nada.

- `prefix_field(prefix, field)` (S3-B4, E5, S3-D75): el `field` de un error del primer pago con el
  prefijo de su campo en la venta (`"amount_cop"` da `"first_payment.amount_cop"`); `None` sigue
  siendo `None`.

- `should_revert(effective_status, agreed_price_cop, paid_cop)` (S3-B5, US-087; D13, N-25): una
  membresía cuyo estado EFECTIVO es `active`, `expiring` o `frozen` y que ya no queda cubierta
  (`covers` falso tras anular un pago) vuelve a `pending_payment`; `pending_payment`, `expired` y
  `cancelled` nunca se revierten.

- `plan_renewal(current, plan, price_cop, today)` (S3-B6, US-088; Q1, D8): `RenewalPlan(start_date,
  end_date, agreed_price_cop)`. Empieza en `next_start_for_renewal(current, today)` (el día
  siguiente al fin de la vigente, incluida la extensión por congelación; hoy si no hay vigente o
  si ya venció), termina en `compute_end_date(inicio, plan)` y cuesta `price_cop`. No muta nada.
- `normalize_cancel_reason(reason)` (S3-B6, US-090; D17, M-7): el motivo de anular una membresía,
  en NFC y recortado; vacío, solo espacios, con caracteres de control o invisibles (`Cc`, `Cf`),
  de menos de `CANCEL_REASON_MIN` (5) o de más de `CANCEL_REASON_MAX` (500) caracteres tras
  recortar es `CancelReasonInvalid` (422, `field="reason"`, sin el valor en el mensaje). Es la
  regla de `SafeText` más el largo del CHECK `cancel_reason_length`: `cancel` la aplica también
  cuando no llega por HTTP.

- `parse_status_filter(raw)` (S3-B7, US-091; D18, L-9): el `status` de `GET /memberships`,
  separado por comas (`"active,expiring"`), como `frozenset[MembershipStatus]`; cada parte se
  recorta y los repetidos se funden; `None`, vacío o solo espacios es `None` (sin filtro); un
  estado desconocido, en mayúsculas o una parte vacía (`"active,"`) es `StatusFilterInvalid`
  (422, `field="status"`, sin el valor en el mensaje).
- `resolve_member_status(items, today)` y `resolve_member_membership(items, today)` (S3-B7,
  US-092; N-26): el estado del SOCIO sobre snapshots con estado EFECTIVO (`compute_status`). Las
  `cancelled` se ignoran. Cada membresía cae en una categoría de `MEMBER_STATUS_PRIORITY`, en
  este orden de prioridad: `current` (cualquier estado que no sea `pending_payment` ni `expired`
  con `start_date <= today`: la vigente), `pending_payment`, `expired` y `future` (no
  `pending_payment` ni `expired`, con `start_date > today`). Decide la de mejor categoría (dentro
  de una misma categoría, la de `end_date` más tardío) y el estado del socio es el estado
  efectivo de esa membresía; sin membresías (o solo canceladas) es `"none"`.
  `resolve_member_membership` devuelve además la que decide (`None` con `"none"`). Es el oráculo
  de la prueba de paridad de `queries.member_status_rank_expr` (S3-D53).
  `member_status_category(m, today)` da la categoría de un snapshot (lo que ordena las dos).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import Final, Literal, Protocol, cast
from uuid import UUID

from app.core.validators import check_visible_text
from app.modules.memberships.exceptions import (
    CancelReasonInvalid,
    StartDateTooFar,
    StartDateTooRetroactive,
    StatusFilterInvalid,
)

MAX_START_AHEAD_DAYS: Final = 366
"""Una venta empieza a más tardar hoy más 366 días (M-4, S3-D47; `renew` no aplica)."""
CANCEL_REASON_MIN: Final = 5
"""Largo mínimo del motivo de anular una membresía tras recortar (D17; CHECK de `0008`)."""
CANCEL_REASON_MAX: Final = 500
"""Largo máximo del motivo de anular una membresía tras recortar (D17; CHECK de `0008`)."""


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
_CONGELABLES: Final = frozenset({MembershipStatus.active, MembershipStatus.expiring})


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


class SnapshotSource(Protocol):
    """Lo que `snapshot` lee: la fila del ORM o una fila de columnas (estado como texto)."""

    @property
    def id(self) -> UUID: ...
    @property
    def status(self) -> str: ...
    @property
    def start_date(self) -> date: ...
    @property
    def end_date(self) -> date: ...
    @property
    def classes_remaining(self) -> int | None: ...


def snapshot(fuente: SnapshotSource) -> MembershipSnapshot:
    """El `MembershipSnapshot` de `fuente` con el estado guardado (docstring del módulo)."""
    return MembershipSnapshot(
        id=fuente.id,
        status=MembershipStatus(fuente.status),
        start_date=fuente.start_date,
        end_date=fuente.end_date,
        classes_remaining=fuente.classes_remaining,
    )


@dataclass(frozen=True, slots=True)
class FreezeLimits:
    """Límites de Q9 (`settings.memberships`): días totales, veces y retroactividad."""

    max_days: int
    max_count: int
    max_retroactive_days: int


@dataclass(frozen=True, slots=True)
class FreezeOutcome:
    """Resultado de `apply_freeze`: la ventana nueva y el fin corrido."""

    window: FreezeWindow
    new_end_date: date


class FreezeError(Exception):
    """Regla de congelación incumplida (D14): `code` estable, `field`, `status` HTTP y un
    `message` opcional (en `freeze_days_exceeded` dice los días que quedan disponibles)."""

    def __init__(
        self, code: str, *, field: str | None = None, status: int = 409, message: str = ""
    ) -> None:
        self.code = code
        self.field = field
        self.status = status
        self.message = message
        super().__init__(code)


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


def apply_freeze(
    m: MembershipSnapshot,
    freezes: Sequence[FreezeWindow],
    frozen_from: date,
    frozen_to: date,
    limits: FreezeLimits,
    today: date,
    expiring_days: int,
) -> FreezeOutcome:
    """Valida la congelación en el orden de D14 y corre el fin (S3-B2). Pura; no muta nada."""
    if compute_status(m, today, expiring_days, freezes) not in _CONGELABLES:
        raise FreezeError("membership_not_freezable")
    if frozen_from > frozen_to:
        raise FreezeError("validation_error", field="frozen_to", status=422)
    if (today - frozen_from).days > limits.max_retroactive_days:
        raise FreezeError("freeze_too_retroactive", field="frozen_from", status=422)
    if not m.start_date <= frozen_from <= m.end_date:
        raise FreezeError("freeze_outside_validity", field="frozen_from", status=422)
    if any(ventana.frozen_to >= today for ventana in freezes):
        raise FreezeError("freeze_already_scheduled")
    if len(freezes) >= limits.max_count:
        raise FreezeError("freeze_limit_reached")
    _check_freeze_days(freezes, frozen_from, frozen_to, limits.max_days)
    ventana = FreezeWindow(frozen_from, frozen_to)
    return FreezeOutcome(window=ventana, new_end_date=m.end_date + timedelta(days=ventana.days))


def _check_freeze_days(
    freezes: Sequence[FreezeWindow], frozen_from: date, frozen_to: date, max_days: int
) -> None:
    """`freeze_days_exceeded` si los días usados más los nuevos pasan `max_days`; el mensaje dice
    los que quedan. Resta fechas (siempre representable): nunca suma días antes de comparar."""
    usados = sum(ventana.days for ventana in freezes)
    disponibles = max(max_days - usados, 0)
    if (frozen_to - frozen_from).days + 1 > disponibles:
        raise FreezeError(
            "freeze_days_exceeded",
            message=f"Quedan {disponibles} días de congelación para esta membresía.",
        )


def prefix_field(prefix: str, field: str | None) -> str | None:
    """`"<prefix>.<field>"`; `None` si el error no tiene campo (E5)."""
    if field is None:
        return None
    return f"{prefix}.{field}"


def should_revert(effective_status: MembershipStatus, agreed_price_cop: int, paid_cop: int) -> bool:
    """Verdadero si la membresía debe volver a `pending_payment` tras anular un pago (S3-B5)."""
    return effective_status in _VIGENTES and not covers(agreed_price_cop, paid_cop)


@dataclass(frozen=True, slots=True)
class RenewalPlan:
    """Resultado de `plan_renewal`: inicio, fin y precio pactado de la renovación (S3-B6)."""

    start_date: date
    end_date: date
    agreed_price_cop: int


def plan_renewal(
    current: MembershipSnapshot | None, plan: PlanTerms, price_cop: int, today: date
) -> RenewalPlan:
    """Fechas y precio de la renovación (S3-B6, Q1; docstring del módulo). Pura."""
    inicio = next_start_for_renewal(current, today)
    return RenewalPlan(
        start_date=inicio, end_date=compute_end_date(inicio, plan), agreed_price_cop=price_cop
    )


def normalize_cancel_reason(reason: str) -> str:
    """El motivo recortado y en NFC; `CancelReasonInvalid` si no es válido (S3-B6)."""
    try:
        motivo = check_visible_text(reason)
    except ValueError as error:
        raise CancelReasonInvalid() from error
    if not CANCEL_REASON_MIN <= len(motivo) <= CANCEL_REASON_MAX:
        raise CancelReasonInvalid()
    return motivo


# Listas y estado del socio (S3-B7) ------------------------------------------------------------

ResolvedStatus = Literal["pending_payment", "active", "expiring", "expired", "frozen", "none"]
"""Estado de membresía de un SOCIO (US-092): los cinco efectivos sin `cancelled`, más `none`."""

RESOLVED_NONE: Final = "none"

MEMBER_STATUS_PRIORITY: Final[tuple[str, ...]] = ("current", "pending_payment", "expired", "future")
"""Categorías de una membresía no cancelada, de mayor a menor prioridad (US-092 criterio 2;
docstring del módulo). La posición es el rango de `queries.member_status_rank_expr`."""


_VALID_STATUSES: Final = frozenset(estado.value for estado in MembershipStatus)


def parse_status_filter(raw: str | None) -> frozenset[MembershipStatus] | None:
    """El filtro `status` separado por comas (docstring del módulo)."""
    if raw is None or not raw.strip():
        return None
    partes = [parte.strip() for parte in raw.split(",")]
    if any(parte not in _VALID_STATUSES for parte in partes):
        raise StatusFilterInvalid()
    return frozenset(MembershipStatus(parte) for parte in partes)


def member_status_category(m: MembershipSnapshot, today: date) -> str:
    """Categoría de US-092 de un snapshot con estado efectivo no cancelado (docstring del
    módulo): `pending_payment` y `expired` por su estado; si no, `current` o `future` por la
    fecha de inicio."""
    if m.status in (MembershipStatus.pending_payment, MembershipStatus.expired):
        return m.status.value
    return "current" if m.start_date <= today else "future"


def resolve_member_membership(
    items: Iterable[MembershipSnapshot], today: date
) -> tuple[ResolvedStatus, MembershipSnapshot | None]:
    """El estado del socio y la membresía que lo decide (docstring del módulo). Mejor categoría
    de `MEMBER_STATUS_PRIORITY`; dentro de una, la de fin más tardío (y luego la de inicio más
    tardío, para no depender del orden de entrada)."""
    candidatas = [m for m in items if m.status != MembershipStatus.cancelled]
    if not candidatas:
        return RESOLVED_NONE, None
    decide = min(
        candidatas,
        key=lambda m: (
            MEMBER_STATUS_PRIORITY.index(member_status_category(m, today)),
            -m.end_date.toordinal(),
            -m.start_date.toordinal(),
        ),
    )
    return cast(ResolvedStatus, decide.status.value), decide


def resolve_member_status(items: Iterable[MembershipSnapshot], today: date) -> ResolvedStatus:
    """El estado del socio (docstring del módulo)."""
    return resolve_member_membership(items, today)[0]
