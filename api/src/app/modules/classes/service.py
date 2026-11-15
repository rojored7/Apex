"""Fachada del service de `classes` (S7-D20). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `slots.py` (S7-A2, US-155): `create_slot`, `update_slot`, `get_slot` y `list_slots`.
- `sessions.py` y `rules.py` (S7-B1, US-156): `generate_sessions`, `GenerateResult`,
  `planned_sessions`, `PlannedSession` y `SlotSpec`; y `events.py`: `SessionGenerated`.
- `queries.py` y `sessions.py` (S7-B2, US-157): `list_sessions`, `get_session`, `create_extra`,
  `cancel_session`; `rules.py`: `parse_week`, `week_range`, `week_of`, `session_status`.
- `attendance.py` (S7-C1, US-159): `check_in`, `list_attendance`, el puerto de membresías
  (`MembershipPort`, `set_membership_port`, `membership_port`, S7-D6) y `MemberCheckedIn`;
  `AttendanceRemoved` (el evento nace en C2 para que memberships lo suscriba) y
  `remove_attendance` (C3, US-161), que lo emite.
`reports.py` (S7-R1, US-162): `attendance_summary`, `member_attendance` y la pura `weekly_summary`.
`queries.py` (S7-R2, US-163): `attended_member_ids` y `last_attendance_for`, que `members` pide por
import perezoso (`# lazy: G-03`) para el filtro y la columna de última asistencia.
"""

from __future__ import annotations

from app.modules.classes.attendance import (
    MembershipPort,
    check_in,
    list_attendance,
    membership_port,
    remove_attendance,
    set_membership_port,
)
from app.modules.classes.events import (
    AttendanceRemoved,
    MemberCheckedIn,
    SessionCancelled,
    SessionGenerated,
)
from app.modules.classes.exceptions import MembershipPortNotRegistered
from app.modules.classes.queries import (
    TODAY_SESSIONS_LIMIT,
    WeekAttendance,
    attended_member_ids,
    get_session,
    last_attendance_for,
    list_sessions,
    today_sessions,
    week_attendance,
)
from app.modules.classes.reports import attendance_summary, member_attendance, weekly_summary
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
    "TODAY_SESSIONS_LIMIT",
    "AttendanceRemoved",
    "GenerateResult",
    "MemberCheckedIn",
    "MembershipPort",
    "MembershipPortNotRegistered",
    "PlannedSession",
    "SessionCancelled",
    "SessionGenerated",
    "SlotSpec",
    "WeekAttendance",
    "attendance_summary",
    "attended_member_ids",
    "cancel_future_sessions",
    "cancel_session",
    "check_in",
    "create_extra",
    "create_slot",
    "generate_sessions",
    "get_session",
    "get_slot",
    "last_attendance_for",
    "list_attendance",
    "list_sessions",
    "list_slots",
    "member_attendance",
    "membership_port",
    "parse_week",
    "planned_sessions",
    "remove_attendance",
    "session_status",
    "set_membership_port",
    "today_sessions",
    "update_slot",
    "week_attendance",
    "week_of",
    "week_range",
    "weekly_summary",
]
