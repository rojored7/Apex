"""Eventos de `classes` (S7-D20). Siempre sin datos personales ni texto libre (S3-D70).

- `SessionGenerated(session_id, slot_id, starts_at)` (S7-B1, US-156): el job, el CLI o el alta de
  una franja crearon una sesión. Los eventos se exportan desde `service.py`.

`SessionCancelled` llega con B2; `MemberCheckedIn` y `AttendanceRemoved` con C1 y C3.
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
