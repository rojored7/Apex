"""Fachada del service de `classes` (S7-D20). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `slots.py` (S7-A2, US-155): `create_slot`, `update_slot`, `get_slot` y `list_slots`.
- `sessions.py` y `rules.py` (S7-B1, US-156): `generate_sessions`, `GenerateResult`,
  `planned_sessions`, `PlannedSession` y `SlotSpec`; y `events.py`: `SessionGenerated`.
- `queries.py` y `sessions.py` (S7-B2, US-157): `list_sessions`, `get_session`, `create_extra`,
  `cancel_session`; `rules.py`: `parse_week`, `week_range`, `week_of`, `session_status`.
En C1 y siguientes suma asistencia y reportes, más el puerto de membresías
(`MembershipPort`, S7-D6).
"""

from __future__ import annotations

from app.modules.classes.events import SessionCancelled, SessionGenerated
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
    cancel_session,
    create_extra,
    generate_sessions,
)
from app.modules.classes.slots import create_slot, get_slot, list_slots, update_slot

__all__ = [
    "GenerateResult",
    "PlannedSession",
    "SessionCancelled",
    "SessionGenerated",
    "SlotSpec",
    "cancel_session",
    "create_extra",
    "create_slot",
    "generate_sessions",
    "get_session",
    "get_slot",
    "list_sessions",
    "list_slots",
    "parse_week",
    "planned_sessions",
    "session_status",
    "update_slot",
    "week_of",
    "week_range",
]
