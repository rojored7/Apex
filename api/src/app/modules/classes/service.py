"""Fachada del service de `classes` (S7-D20). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `slots.py` (S7-A2, US-155): `create_slot`, `update_slot`, `get_slot` y `list_slots`.
En B1, B2, C1 y siguientes suma sesiones, asistencia y reportes, más el puerto de membresías
(`MembershipPort`, S7-D6) y los eventos de `events.py`.
"""

from __future__ import annotations

from app.modules.classes.slots import create_slot, get_slot, list_slots, update_slot

__all__ = ["create_slot", "get_slot", "list_slots", "update_slot"]
