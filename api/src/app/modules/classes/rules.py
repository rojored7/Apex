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
    "week": "La semana debe ser AAAA-Www, de 2020 a 2100, y existir en el calendario ISO.",
    "starts_at": "La sesión debe empezar entre ayer y los próximos 90 días.",
    "from": "Indica `from` y `to` juntos, y no los mezcles con `week`.",
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
    slots: Sequence[SlotLike],
    from_date: date,
    to_date: date,
    *,
    not_before: datetime | None = None,
) -> list[PlannedSession]:
    """Sesiones de las franjas activas entre `from_date` y `to_date` (ambas incluidas).

    Por cada franja activa y cada fecha del rango cuyo día de la semana está en `weekdays` y es
    `>= valid_from`: `starts_at` es la fecha con `start_time` en Bogotá pasada a UTC (Colombia no
    tiene horario de verano). Con `not_before` se descartan las que empiezan antes de ese instante
    (una clase de hoy cuya hora ya pasó; la que empieza justo en `not_before` se queda). Orden:
    `starts_at` y luego el id de la franja."""
    desde = from_date
    salida: list[PlannedSession] = []
    for franja in slots:
        if not franja.is_active:
            continue
        hora = time.fromisoformat(franja.start_time)
        dias = set(franja.weekdays)
        dia = max(desde, franja.valid_from)
        while dia <= to_date:
            inicio = datetime.combine(dia, hora, tzinfo=BOGOTA).astimezone(UTC)
            if dia.weekday() in dias and (not_before is None or inicio >= not_before):
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


WEEK_YEAR_MIN: Final = 2020
WEEK_YEAR_MAX: Final = 2100
MAX_RANGE_DAYS: Final = 62
EXTRA_MAX_AHEAD_DAYS: Final = 90
SESSION_STATUSES_OUT: Final = ("scheduled", "cancelled", "done")


WEEK_PATTERN: Final = re.compile(r"([0-9]{4})-W([0-9]{2})")


def parse_week(week: str) -> tuple[int, int]:
    r"""`"2026-W43"` -> `(2026, 43)`; 422 `field = "week"` si no existe esa semana ISO.

    Solo dígitos ASCII (no `\d`) y años de 2020 a 2100: con `9999-W52` el cálculo del lunes
    siguiente desbordaría (`OverflowError`, un 500; S7-D32 L-1)."""
    encontrado = WEEK_PATTERN.fullmatch(week)
    if encontrado is None:
        raise _invalido("week")
    anio, semana = int(encontrado.group(1)), int(encontrado.group(2))
    if not WEEK_YEAR_MIN <= anio <= WEEK_YEAR_MAX:
        raise _invalido("week")
    try:
        date.fromisocalendar(anio, semana, 1)
    except ValueError:
        raise _invalido("week") from None
    return anio, semana


def _midnight_utc(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=BOGOTA).astimezone(UTC)


def week_range(year: int, week: int) -> tuple[datetime, datetime]:
    """Lunes 00:00 al lunes siguiente 00:00 de Bogotá, en UTC (`[desde, hasta)`)."""
    lunes = date.fromisocalendar(year, week, 1)
    return _midnight_utc(lunes), _midnight_utc(lunes + timedelta(days=7))


def week_of(day: date) -> str:
    """La semana ISO de una fecha civil, como `"2026-W43"`."""
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def date_range_utc(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    """`from` a `to` (ambos días incluidos, de Bogotá) como `[desde, hasta)` en UTC."""
    return _midnight_utc(from_date), _midnight_utc(to_date + timedelta(days=1))


def local_date(starts_at: datetime) -> date:
    """La fecha civil de Bogotá de un instante."""
    return starts_at.astimezone(BOGOTA).date()


def session_status(status: str, starts_at: datetime, duration_min: int, now: datetime) -> str:
    """`cancelled`, `done` (programada cuya hora de fin ya pasó) o `scheduled`."""
    if status == "cancelled":
        return "cancelled"
    if now >= starts_at + timedelta(minutes=duration_min):
        return "done"
    return "scheduled"


def validate_extra_start(starts_at: datetime, now: datetime) -> None:
    """Una sesión extra empieza entre el inicio de ayer (Bogotá) y 90 días adelante."""
    ayer = _midnight_utc(local_date(now) - timedelta(days=1))
    if starts_at < ayer or starts_at > now + timedelta(days=EXTRA_MAX_AHEAD_DAYS):
        raise _invalido("starts_at")
