"""Eventos de `classes` (S7-D20). Siempre sin datos personales ni texto libre (S3-D70).

- `SessionGenerated(session_id, slot_id, starts_at)` (S7-B1, US-156): el job, el CLI o el alta de
  una franja crearon una sesión. Los eventos se exportan desde `service.py`.

`SessionCancelled(session_id, slot_id, starts_at)` (S7-B2, US-157) no lleva el motivo (L-2).
`MemberCheckedIn` (C1, US-159) y `AttendanceRemoved` (C3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionGenerated(DomainEvent):
    session_id: UUID
    slot_id: UUID | None
    starts_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionCancelled(DomainEvent):
    """Una sesión se canceló. Sin el motivo: es texto libre (S7-D32, L-2)."""

    session_id: UUID
    slot_id: UUID | None
    starts_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberCheckedIn(DomainEvent):
    """Un socio hizo check-in (S7-D12). Sin nombres ni texto libre (S3-D70).

    `membership_id` es la membresía que decidió (nula sin membresía vigente ese día, S7-D25).
    Memberships descuenta la clase (US-160)."""

    attendance_id: UUID
    session_id: UUID
    member_id: UUID
    membership_id: UUID | None
    membership_status: str
    flags: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AttendanceRemoved(DomainEvent):
    """Una asistencia se quitó (S7-D13, US-161): memberships devuelve la clase que descontó.

    `membership_id` es la membresía que decidió el check-in (nula si no había) y
    `membership_status` el estado que tenía entonces: solo `active` o `expiring` descontaron
    (S7-D14). Sin nombres ni el motivo, que es texto libre (S3-D70)."""

    attendance_id: UUID
    session_id: UUID
    member_id: UUID
    membership_id: UUID | None
    membership_status: str
