"""Fachada del service de `wods` (S8-A1). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `movements.py` (S8-A1, US-165): `create_movement`, `update_movement`, `get_movement` y
  `list_movements`.
- `benchmarks.py` (S8-A2, US-166): `create_benchmark`, `update_benchmark`, `get_benchmark` y
  `list_benchmarks`.
- `seed.py` (S8-A2, N-46): `seed_benchmarks` (la usa `cli_ops/seed_benchmarks.py`).
- `rules.py`: `normalize_movement_name`.
"""

from __future__ import annotations

from app.modules.wods.benchmarks import (
    create_benchmark,
    get_benchmark,
    list_benchmarks,
    update_benchmark,
)
from app.modules.wods.movements import (
    create_movement,
    get_movement,
    list_movements,
    update_movement,
)
from app.modules.wods.rules import normalize_movement_name
from app.modules.wods.seed import seed_benchmarks

__all__ = [
    "create_benchmark",
    "create_movement",
    "get_benchmark",
    "get_movement",
    "list_benchmarks",
    "list_movements",
    "normalize_movement_name",
    "seed_benchmarks",
    "update_benchmark",
    "update_movement",
]
