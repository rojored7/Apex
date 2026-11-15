"""Fachada del service de `wods` (S8-A1). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `movements.py` (S8-A1, US-165): `create_movement`, `update_movement`, `get_movement` y
  `list_movements`.
- `benchmarks.py` (S8-A2, US-166): `create_benchmark`, `update_benchmark`, `get_benchmark` y
  `list_benchmarks`.
- `seed.py` (S8-A2, N-46): `seed_benchmarks` (la usa `cli_ops/seed_benchmarks.py`).
- `programming.py` (S8-A3, US-166, US-167): `create_wod`, `update_wod`, `get_wod` y `list_wods`.
- `probe.py` (S8-A3): el puerto `ResultsProbe` (`set_results_probe`, `results_probe`); `results`
  lo registra (B1). Mientras no exista, esta fachada registra `NoResultsYet` (cero resultados).
- `events.py`: `WodPublished`. `rules.py`: `normalize_movement_name`.
"""

from __future__ import annotations

from app.modules.wods.benchmarks import (
    create_benchmark,
    get_benchmark,
    list_benchmarks,
    update_benchmark,
)
from app.modules.wods.events import WodPublished
from app.modules.wods.movements import (
    create_movement,
    get_movement,
    list_movements,
    update_movement,
)
from app.modules.wods.probe import (
    NoResultsYet,
    ResultsProbe,
    current_results_probe,
    results_probe,
    set_results_probe,
)
from app.modules.wods.programming import create_wod, get_wod, list_wods, update_wod
from app.modules.wods.rules import normalize_movement_name
from app.modules.wods.seed import seed_benchmarks

if current_results_probe() is None:  # B1 (results) lo reemplaza con el puerto real
    set_results_probe(NoResultsYet())

__all__ = [
    "NoResultsYet",
    "ResultsProbe",
    "WodPublished",
    "create_benchmark",
    "create_movement",
    "create_wod",
    "current_results_probe",
    "get_benchmark",
    "get_movement",
    "get_wod",
    "list_benchmarks",
    "list_movements",
    "list_wods",
    "normalize_movement_name",
    "results_probe",
    "seed_benchmarks",
    "set_results_probe",
    "update_benchmark",
    "update_movement",
    "update_wod",
]
