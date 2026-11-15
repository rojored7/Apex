"""Reglas puras de `results` (S8-B1, S8-D12, N-43, L-2). Sin sesión ni reloj.

`validate_score` valida la marca contra el tipo del WOD y devuelve los valores que se guardan.
Reglas por tipo (los campos ajenos al tipo dan 422 con su `field`):
- `time`: `seconds` (1 a 86.400; con time cap no lo supera). Con `capped`, el WOD tiene time cap,
  el cliente NO manda `seconds` (se fija igual al cap) y `reps` (las completadas) es obligatorio.
- `rounds_reps`: `rounds` y `reps` obligatorios. `reps`: `reps`. `load`: `load_g`.
- `capped` solo vale con `time` (N-43).
- `scaled_movement_ids` (L-2): solo con `scaled`, sin repetidos, hasta 30 y todos del WOD.
Ceros válidos salvo `seconds`; ningún negativo.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.modules.results.exceptions import ResultValidationError

SECONDS_MAX: Final = 86_400
ROUNDS_MAX: Final = 1_000
REPS_MAX: Final = 100_000
LOAD_MAX_G: Final = 1_000_000
SCALED_IDS_MAX: Final = 30
_FIELDS: Final = ("seconds", "rounds", "reps", "load_g")
_USED: Final[dict[str, tuple[str, ...]]] = {
    "time": ("seconds",),
    "rounds_reps": ("rounds", "reps"),
    "reps": ("reps",),
    "load": ("load_g",),
}


@dataclass(frozen=True, slots=True)
class ScoreValues:
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    scaled_movement_ids: tuple[UUID, ...]


def _fail(field: str, message: str) -> ResultValidationError:
    return ResultValidationError(message=message, field=field)


def _check_range(name: str, value: int | None, low: int, high: int) -> None:
    if value is not None and not low <= value <= high:
        raise _fail(name, "El valor está fuera del rango permitido.")


def _check_scaled(
    level: str, ids: Sequence[UUID], wod_movement_ids: Collection[UUID]
) -> tuple[UUID, ...]:
    if not ids:
        return ()
    if level != "scaled":
        raise _fail("scaled_movement_ids", "Los movimientos escalados solo valen con nivel scaled.")
    if len(ids) > SCALED_IDS_MAX or len(set(ids)) != len(ids):
        raise _fail("scaled_movement_ids", "Los movimientos escalados no son válidos.")
    if not set(ids) <= set(wod_movement_ids):
        raise _fail("scaled_movement_ids", "Hay movimientos que no son de este WOD.")
    return tuple(ids)


def validate_score(
    *,
    score_type: str,
    time_cap_s: int | None,
    level: str,
    seconds: int | None,
    rounds: int | None,
    reps: int | None,
    load_g: int | None,
    capped: bool,
    scaled_movement_ids: Sequence[UUID],
    wod_movement_ids: Collection[UUID],
) -> ScoreValues:
    values = {"seconds": seconds, "rounds": rounds, "reps": reps, "load_g": load_g}
    for name, value in values.items():
        if value is not None and value < 0:
            raise _fail(name, "El valor no puede ser negativo.")
    _check_range("seconds", seconds, 1, SECONDS_MAX)
    _check_range("rounds", rounds, 0, ROUNDS_MAX)
    _check_range("reps", reps, 0, REPS_MAX)
    _check_range("load_g", load_g, 0, LOAD_MAX_G)
    if capped and score_type != "time":
        raise _fail("capped", "Solo un WOD de tiempo se corta por time cap.")
    usados = _USED.get(score_type)
    if usados is None:
        raise _fail("wod_id", "Este WOD no registra resultados.")
    permitidos = set(usados) | ({"reps"} if capped else set())
    for name in _FIELDS:
        if values[name] is not None and name not in permitidos:
            raise _fail(name, "Este campo no corresponde al tipo de marca del WOD.")
    if capped:
        if time_cap_s is None:
            raise _fail("capped", "El WOD no tiene time cap.")
        if seconds is not None:
            raise _fail("seconds", "Con time cap alcanzado los segundos los fija el WOD.")
        if reps is None:
            raise _fail("reps", "Indica las repeticiones completadas.")
        seconds = time_cap_s
    else:
        for name in usados:
            if values[name] is None:
                raise _fail(name, "Este campo es obligatorio para este WOD.")
        if score_type == "time" and time_cap_s is not None and (seconds or 0) > time_cap_s:
            raise _fail("seconds", "El tiempo supera el time cap: marca el corte por time cap.")
    ids = _check_scaled(level, scaled_movement_ids, wod_movement_ids)
    return ScoreValues(seconds, rounds, reps, load_g, capped, ids)
