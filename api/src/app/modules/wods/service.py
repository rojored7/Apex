"""Fachada del service de `wods` (S8-A1). Lo único que importan los demás módulos.

Reexporta lo público de los archivos privados del módulo:
- `movements.py` (S8-A1, US-165): `create_movement`, `update_movement`, `get_movement` y
  `list_movements`.
- `benchmarks.py` (S8-A2, US-166): `create_benchmark`, `update_benchmark`, `get_benchmark` y
  `list_benchmarks`.
- `seed.py` (S8-A2, N-46): `seed_benchmarks` (la usa `cli_ops/seed_benchmarks.py`).
- `programming.py` (S8-A3, US-166, US-167): `create_wod`, `update_wod`, `get_wod` y `list_wods`.
- `probe.py` (S8-A3): el puerto `ResultsProbe` (`set_results_probe`, `results_probe`); `results`
  lo registra al importarse (B1). Sin puerto, lo que depende de resultados falla cerrado.
- `catalog.py` (S8-B1): `scoring_for` (el WOD `FOR SHARE` y lo que `results` valida) y, desde
  S8-B4, `titles_for` (título, fecha y tipo de marca por WOD, sin candados).
- `events.py`: `WodPublished`. `rules.py`: `normalize_movement_name`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods.benchmarks import (
    create_benchmark,
    get_benchmark,
    list_benchmarks,
    update_benchmark,
)
from app.modules.wods.catalog import (
    WOD_IDS_MAX,
    BenchmarkRef,
    MovementRef,
    WodRecordMeta,
    WodScoring,
    WodTitle,
    benchmark_for_share,
    benchmark_refs,
    day_wod_ids,
    ensure_wod,
    movement_refs,
    movements_by_id,
    record_meta_for,
    scoring_for,
    titles_for,
    today_title,
    wod_date,
    wod_ids_with_primary,
)
from app.modules.wods.events import WodPublished
from app.modules.wods.movements import (
    create_movement,
    get_movement,
    list_movements,
    update_movement,
)
from app.modules.wods.probe import (
    RecordsProbe,
    ResultsProbe,
    current_records_probe,
    current_results_probe,
    records_probe,
    results_probe,
    set_records_probe,
    set_results_probe,
)
from app.modules.wods.programming import create_wod, get_wod, list_wods, today_card, update_wod
from app.modules.wods.rules import normalize_movement_name
from app.modules.wods.seed import seed_benchmarks


async def movement_for_record(session: AsyncSession, movement_id: UUID) -> MovementRef | None:
    """El movimiento con `FOR SHARE` y datos frescos, como dato plano (S9-D6, S9-D9, US-180).
    Envoltura pública de `catalog.movements_by_id`; `None` si no existe."""
    mov = (await movements_by_id(session, [movement_id])).get(movement_id)
    return None if mov is None else MovementRef(mov.id, mov.name, mov.unit, mov.is_active)


async def benchmark_for_record(session: AsyncSession, benchmark_id: UUID) -> BenchmarkRef | None:
    """El benchmark con `FOR SHARE` y datos frescos, como dato plano (S9-D6, S9-D9, US-180).
    Envoltura pública de `catalog.benchmark_for_share`; `None` si no existe."""
    bm = await benchmark_for_share(session, benchmark_id)
    return None if bm is None else BenchmarkRef(bm.id, bm.name, bm.score_type)


__all__ = [
    "WOD_IDS_MAX",
    "BenchmarkRef",
    "MovementRef",
    "RecordsProbe",
    "ResultsProbe",
    "WodPublished",
    "WodRecordMeta",
    "WodScoring",
    "WodTitle",
    "benchmark_for_record",
    "benchmark_refs",
    "create_benchmark",
    "create_movement",
    "create_wod",
    "current_records_probe",
    "current_results_probe",
    "day_wod_ids",
    "ensure_wod",
    "get_benchmark",
    "get_movement",
    "get_wod",
    "list_benchmarks",
    "list_movements",
    "list_wods",
    "movement_for_record",
    "movement_refs",
    "normalize_movement_name",
    "record_meta_for",
    "records_probe",
    "results_probe",
    "scoring_for",
    "seed_benchmarks",
    "set_records_probe",
    "set_results_probe",
    "titles_for",
    "today_card",
    "today_title",
    "update_benchmark",
    "update_movement",
    "update_wod",
    "wod_date",
    "wod_ids_with_primary",
]
