"""Eventos que emite `memberships` (S3-B1; L7: se definen en el emisor y se re-exportan desde
`service.py`). Privado (D7): los suscriptores los importan de `memberships.service`.

Solo ids, fechas y montos: ningún evento lleva datos personales (S3-D70).

Eventos de transición (S4A-B2, US-094; S4A-D1): `MembershipExpiring` y `MembershipExpired` los
emite solo el recálculo diario (`expirations.recompute_statuses`, el job `expirations` del worker
o `recompute-memberships` del CLI) cuando la columna `status` guardada pasa a `expiring` o a
`expired` (`rules.transition_event`). Hasta el Sprint 5 no tienen suscriptores (ni siquiera la
caché del resumen: el resumen se deriva con `status_expr`, S4A-D1).

Regla de `on_date` para los consumidores (S4A-D48 punto 3, M-4): `on_date` es el "hoy" de Bogotá
con el que corrió el recálculo; con `--date ... --simulate` (solo en desarrollo, contra una base
de simulación) puede ser un día futuro. Un consumidor (Notifications, Sprint 5) **descarta** todo
`MembershipExpiring` o `MembershipExpired` cuyo `on_date` no sea `today_bogota()` ni el día
anterior: así una corrida simulada o atrasada nunca avisa a un socio fuera de fecha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipSold(DomainEvent):
    """Una venta (o renovación, `renewal=True`, B6) quedó insertada en la transacción."""

    membership_id: UUID
    member_id: UUID
    plan_id: UUID
    agreed_price_cop: int
    start_date: date
    end_date: date
    renewal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipFrozen(DomainEvent):
    """Una congelación quedó insertada y el fin de la membresía corrido (S3-B2, D14)."""

    membership_id: UUID
    member_id: UUID
    frozen_from: date
    frozen_to: date
    days: int
    end_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipActivated(DomainEvent):
    """Una `pending_payment` quedó cubierta por sus pagos no anulados y pasó al estado efectivo
    (`active`, `expiring`, `frozen` o `expired`; S3-B4, D11). Lo emite `on_payment_registered`."""

    membership_id: UUID
    member_id: UUID
    status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipActivationReverted(DomainEvent):
    """Una membresía `active`, `expiring` o `frozen` (estado efectivo) dejó de estar cubierta al
    anularse un pago y volvió a `pending_payment`, conservando congelaciones y `end_date` (S3-B5,
    US-087, D13, N-25). `previous_status` es el estado efectivo antes de revertir. Lo emite
    `on_payment_voided`."""

    membership_id: UUID
    member_id: UUID
    previous_status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipCancelled(DomainEvent):
    """Una membresía quedó anulada (S3-B6, US-090). Lleva el largo del motivo (`reason_len`),
    nunca su texto (M-7, S3-D70). Lo emite `lifecycle.cancel`."""

    membership_id: UUID
    member_id: UUID
    reason_len: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipExpiring(DomainEvent):
    """La columna `status` pasó a `expiring` desde `active` o `frozen` en el recálculo diario
    (S4A-B2, S4A-D1). `on_date` es el día de Bogotá del recálculo (regla de `on_date` en el
    docstring del módulo)."""

    membership_id: UUID
    member_id: UUID
    end_date: date
    on_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipExpired(DomainEvent):
    """La columna `status` pasó a `expired` (desde cualquier estado candidato) en el recálculo
    diario (S4A-B2, S4A-D1). Un `active` que venció hace días emite solo este evento."""

    membership_id: UUID
    member_id: UUID
    end_date: date
    on_date: date
