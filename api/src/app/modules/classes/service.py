"""Fachada del service de `classes` (S7-D20). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `slots.py` (S7-A2, US-155): `create_slot`, `update_slot`, `get_slot` y `list_slots`.
- `sessions.py` y `rules.py` (S7-B1, US-156): `generate_sessions`, `GenerateResult`,
  `planned_sessions`, `PlannedSession` y `SlotSpec`; y `events.py`: `SessionGenerated`.
En B2, C1 y siguientes suma cancelar, asistencia y reportes, más el puerto de membresías
(`MembershipPort`, S7-D6).
"""

from __future__ import annotations

from app.modules.classes.events import SessionGenerated
from app.modules.classes.rules import PlannedSession, SlotSpec, planned_sessions
from app.modules.classes.sessions import GenerateResult, generate_sessions
from app.modules.classes.slots import create_slot, get_slot, list_slots, update_slot

__all__ = [
    "GenerateResult",
    "PlannedSession",
    "SessionGenerated",
    "SlotSpec",
    "create_slot",
    "generate_sessions",
    "get_slot",
    "list_slots",
    "planned_sessions",
    "update_slot",
]
