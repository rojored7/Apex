"""Reglas puras de clases (S7-D9, S7-D11; US-155). Sin sesión ni reloj: se prueban sin base.

- `validate_slot(weekdays, start_time, duration_min, capacity)`: de 1 a 7 días de 0 (lunes) a 6
  (domingo) sin repetir, `HH:MM` válido (hora local de Bogotá, N-40), duración de 15 a 240 minutos
  y cupo de 1 a 100. Lanza `ClassValidationError` con `field` y sin repetir el valor.
- `normalize_weekdays(weekdays)`: los días sin repetir y ordenados (como se guardan).
- `planned_sessions(slots, from_date, to_date)`: las sesiones que piden las franjas activas en un
  rango de fechas civiles de Bogotá (US-156, S7-D10), con la hora en UTC.
- `slots_overlap(a_days, a_time, b_days, b_time)`: dos franjas chocan si comparten algún día y la
  misma hora de inicio (US-155 CA3).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final, Protocol
from uuid import UUID

from app.core.clock import BOGOTA
from app.modules.classes.exceptions import ClassValidationError

WEEKDAY_MIN: Final = 0
WEEKDAY_MAX: Final = 6
DURATION_MIN: Final = 15
DURATION_MAX: Final = 240
CAPACITY_MIN: Final = 1
CAPACITY_MAX: Final = 100
NAME_MAX_LENGTH: Final = 40
# `[0-9]` y no `\d`: `\d` acepta dígitos Unicode (misma corrección que HHMM_PATTERN de settings).
TIME_PATTERN: Final = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")

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


class SlotLike(Protocol):
    """Lo que `planned_sessions` lee de una franja (la fila ORM y `SlotSpec` lo cumplen)."""

    @property
    def id(self) -> UUID: ...
    @property
    def weekdays(self) -> Sequence[int]: ...
    @property
    def start_time(self) -> str: ...
    @property
    def duration_min(self) -> int: ...
    @property
    def capacity(self) -> int: ...
    @property
    def default_coach_id(self) -> UUID | None: ...
    @property
    def name(self) -> str | None: ...
    @property
    def valid_from(self) -> date: ...
    @property
    def is_active(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class SlotSpec:
    """Una franja como valor puro (pruebas y llamadas sin base)."""

    id: UUID
    weekdays: Sequence[int]
    start_time: str
    duration_min: int
    capacity: int
    default_coach_id: UUID | None
    name: str | None
    valid_from: date
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class PlannedSession:
    """Una sesión que debe existir: copia de la franja en esa fecha."""

    slot_id: UUID
    session_date: date
    starts_at: datetime
    duration_min: int
    capacity: int
    coach_id: UUID | None
    name: str | None


def planned_sessions(
    slots: Sequence[SlotLike], from_date: date, to_date: date
) -> list[PlannedSession]:
    """Sesiones de las franjas activas entre `from_date` y `to_date` (ambas incluidas).

    Por cada franja activa y cada fecha del rango cuyo día de la semana está en `weekdays` y es
    `>= valid_from`: `starts_at` es la fecha con `start_time` en Bogotá pasada a UTC (Colombia no
    tiene horario de verano). Orden: `starts_at` y luego el id de la franja."""
    desde = from_date
    salida: list[PlannedSession] = []
    for franja in slots:
        if not franja.is_active:
            continue
        hora = time.fromisoformat(franja.start_time)
        dias = set(franja.weekdays)
        dia = max(desde, franja.valid_from)
        while dia <= to_date:
            if dia.weekday() in dias:
                inicio = datetime.combine(dia, hora, tzinfo=BOGOTA).astimezone(UTC)
                salida.append(
                    PlannedSession(
                        slot_id=franja.id,
                        session_date=dia,
                        starts_at=inicio,
                        duration_min=franja.duration_min,
                        capacity=franja.capacity,
                        coach_id=franja.default_coach_id,
                        name=franja.name,
                    )
                )
            dia += timedelta(days=1)
    salida.sort(key=lambda p: (p.starts_at, str(p.slot_id)))
    return salida
