"""Fachada del service de `classes` (S7-D20). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `slots.py` (S7-A2, US-155): `create_slot`, `update_slot`, `get_slot` y `list_slots`.
- `sessions.py` y `rules.py` (S7-B1, US-156): `generate_sessions`, `GenerateResult`,
  `planned_sessions`, `PlannedSession` y `SlotSpec`; y `events.py`: `SessionGenerated`.
- `queries.py` y `sessions.py` (S7-B2, US-157): `list_sessions`, `get_session`, `create_extra`,
  `cancel_session`; `rules.py`: `parse_week`, `week_range`, `week_of`, `session_status`.
- `attendance.py` (S7-C1, US-159): `check_in`, `list_attendance`, el puerto de membresías
  (`MembershipPort`, `set_membership_port`, `membership_port`, S7-D6) y `MemberCheckedIn`;
  `AttendanceRemoved` (el evento nace en C2 para que memberships lo suscriba; lo emite C3).
Los reportes llegan con R1.
"""

from __future__ import annotations

from app.modules.classes.attendance import (
    MembershipPort,
    check_in,
    list_attendance,
    membership_port,
    set_membership_port,
)
from app.modules.classes.events import (
    AttendanceRemoved,
    MemberCheckedIn,
    SessionCancelled,
    SessionGenerated,
)
from app.modules.classes.exceptions import MembershipPortNotRegistered
from app.modules.classes.queries import get_session, list_sessions
from app.modules.classes.rules import (
    PlannedSession,
    SlotSpec,
    parse_week,
    planned_sessions,
    session_status,
    week_of,
    week_range,
)
from app.modules.classes.sessions import (
    GenerateResult,
    cancel_future_sessions,
    cancel_session,
    create_extra,
    generate_sessions,
)
from app.modules.classes.slots import create_slot, get_slot, list_slots, update_slot

__all__ = [
    "AttendanceRemoved",
    "GenerateResult",
    "MemberCheckedIn",
    "MembershipPort",
    "MembershipPortNotRegistered",
    "PlannedSession",
    "SessionCancelled",
    "SessionGenerated",
    "SlotSpec",
    "cancel_future_sessions",
    "cancel_session",
    "check_in",
    "create_extra",
    "create_slot",
    "generate_sessions",
    "get_session",
    "get_slot",
    "list_attendance",
    "list_sessions",
    "list_slots",
    "membership_port",
    "parse_week",
    "planned_sessions",
    "session_status",
    "set_membership_port",
    "update_slot",
    "week_of",
    "week_range",
]
