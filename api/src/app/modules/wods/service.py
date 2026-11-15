"""Fachada del service de `wods` (S8-A1). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `movements.py` (S8-A1, US-165): `create_movement`, `update_movement`, `get_movement` y
  `list_movements`.
- `rules.py`: `normalize_movement_name`.
"""

from __future__ import annotations

from app.modules.wods.movements import (
    create_movement,
    get_movement,
    list_movements,
    update_movement,
)
from app.modules.wods.rules import normalize_movement_name

__all__ = [
    "create_movement",
    "get_movement",
    "list_movements",
    "normalize_movement_name",
    "update_movement",
]
