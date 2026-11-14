"""Reglas puras de clases (S7-D9, S7-D11; US-155). Sin sesión ni reloj: se prueban sin base.

- `validate_slot(weekdays, start_time, duration_min, capacity)`: de 1 a 7 días de 0 (lunes) a 6
  (domingo) sin repetir, `HH:MM` válido (hora local de Bogotá, N-40), duración de 15 a 240 minutos
  y cupo de 1 a 100. Lanza `ClassValidationError` con `field` y sin repetir el valor.
- `normalize_weekdays(weekdays)`: los días sin repetir y ordenados (como se guardan).
- `slots_overlap(a_days, a_time, b_days, b_time)`: dos franjas chocan si comparten algún día y la
  misma hora de inicio (US-155 CA3).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from typing import Final

from app.modules.classes.exceptions import ClassValidationError

WEEKDAY_MIN: Final = 0
WEEKDAY_MAX: Final = 6
DURATION_MIN: Final = 15
DURATION_MAX: Final = 240
CAPACITY_MIN: Final = 1
CAPACITY_MAX: Final = 100
NAME_MAX_LENGTH: Final = 40
TIME_PATTERN: Final = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_MENSAJES: Final = {
    "weekdays": "Elige de 1 a 7 días distintos, de lunes (0) a domingo (6).",
    "start_time": "La hora de inicio debe ser HH:MM entre 00:00 y 23:59.",
    "duration_min": "La duración debe estar entre 15 y 240 minutos.",
    "capacity": "El cupo debe estar entre 1 y 100.",
}


def _invalido(campo: str) -> ClassValidationError:
    return ClassValidationError(message=_MENSAJES[campo], field=campo)


def normalize_weekdays(weekdays: Collection[int]) -> list[int]:
    """Los días sin repetir y de lunes a domingo."""
    return sorted(set(weekdays))


def validate_slot(
    weekdays: Sequence[int], start_time: str, duration_min: int, capacity: int
) -> None:
    """Valida los campos de una franja; el primero que falla da `ClassValidationError`."""
    dias = list(weekdays)
    if (
        not dias
        or len(dias) > WEEKDAY_MAX + 1
        or len(set(dias)) != len(dias)
        or any(isinstance(d, bool) or not WEEKDAY_MIN <= d <= WEEKDAY_MAX for d in dias)
    ):
        raise _invalido("weekdays")
    if not TIME_PATTERN.fullmatch(start_time):
        raise _invalido("start_time")
    if not DURATION_MIN <= duration_min <= DURATION_MAX:
        raise _invalido("duration_min")
    if not CAPACITY_MIN <= capacity <= CAPACITY_MAX:
        raise _invalido("capacity")


def slots_overlap(
    a_days: Collection[int], a_time: str, b_days: Collection[int], b_time: str
) -> bool:
    """¿Comparten algún día y la misma hora de inicio? (US-155 CA3)."""
    return a_time == b_time and not set(a_days).isdisjoint(b_days)
