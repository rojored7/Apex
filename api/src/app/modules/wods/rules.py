"""Reglas puras de `wods` (S8-A1, US-165; S8-D5). Sin sesión ni reloj: se prueban sin base.

- `normalize_movement_name(name)`: NFKC, recorte, espacios internos colapsados y minúsculas; es la
  clave de unicidad del catálogo (`name_norm`). Si queda vacío o pasa de 60 caracteres (NFKC puede
  expandir), `WodsValidationError` con `field = "name"` y sin repetir el valor.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from app.modules.wods.exceptions import WodsValidationError

NAME_MAX_LENGTH: Final = 60
DESCRIPTION_MAX_LENGTH: Final = 2000
CATEGORIES: Final = ("weightlifting", "gymnastics", "monostructural", "other")
UNITS: Final = ("kg", "reps", "m", "cal", "s")
_ESPACIOS: Final = re.compile(r"\s+")
_MENSAJE: Final = "El nombre debe tener de 1 a 60 caracteres visibles."


def normalize_movement_name(name: str) -> str:
    texto = _ESPACIOS.sub(" ", unicodedata.normalize("NFKC", name)).strip().lower()
    if not texto or len(texto) > NAME_MAX_LENGTH:
        raise WodsValidationError(message=_MENSAJE, field="name")
    return texto


def clean_movement_name(name: str) -> str:
    """El nombre que se guarda y se muestra: recorte y espacios internos colapsados (sin cambiar
    mayúsculas ni tildes). `SafeText` ya normalizó a NFC."""
    return _ESPACIOS.sub(" ", name).strip()


# S8-A3 (US-166, US-167, S8-D7, S8-D8, S8-D41) -------------------------------------------------

TITLE_MAX_LENGTH: Final = 80
MAX_MOVEMENTS: Final = 30
TIME_CAP_MAX_S: Final = 14_400
LOAD_MAX_G: Final = 1_000_000
CAPPED_SCORE_TYPES: Final = ("time", "rounds_reps")
WEEK_MIN_YEAR: Final = 2020
WEEK_MAX_YEAR: Final = 2100


@dataclass(frozen=True, slots=True)
class MovementSpec:
    """Lo que `validate_wod` necesita de cada movimiento: su lugar, si es el principal, la unidad
    del catálogo (las cargas solo valen con `kg`) y las cargas RX en gramos."""

    position: int
    is_primary: bool
    unit: str
    load_rx_m_g: int | None = None
    load_rx_f_g: int | None = None


def validate_wod(
    score_type: str, time_cap_s: int | None, movements: Sequence[MovementSpec]
) -> None:
    """Reglas de forma de un WOD (US-166, S8-D7). `WodsValidationError` con `field`.

    1 a 30 movimientos con posiciones 1..n (en cualquier orden de la lista), a lo sumo un
    principal, `time_cap_s` de 1 a 14.400 y solo con `time|rounds_reps`, y cargas RX solo en
    movimientos cuya unidad es `kg`. Las cargas ya llegan acotadas (0 a 1.000.000 g) por el esquema.
    """
    if score_type in CAPPED_SCORE_TYPES:
        if time_cap_s is not None and not 1 <= time_cap_s <= TIME_CAP_MAX_S:
            raise WodsValidationError(
                message="El time cap debe estar entre 1 y 14.400 segundos.", field="time_cap_s"
            )
    elif time_cap_s is not None:
        raise WodsValidationError(
            message="El time cap solo vale con tipo de marca de tiempo o de rondas y repeticiones.",
            field="time_cap_s",
        )
    if not 1 <= len(movements) <= MAX_MOVEMENTS:
        raise WodsValidationError(
            message="El WOD debe tener de 1 a 30 movimientos.", field="movements"
        )
    if sorted(m.position for m in movements) != list(range(1, len(movements) + 1)):
        raise WodsValidationError(
            message="Las posiciones deben ser 1, 2, 3... sin saltos ni repetidas.",
            field="movements",
        )
    if sum(1 for m in movements if m.is_primary) > 1:
        raise WodsValidationError(
            message="Solo puede haber un movimiento principal.", field="movements"
        )
    for indice, movimiento in enumerate(movements):
        for lado, carga in (("m", movimiento.load_rx_m_g), ("f", movimiento.load_rx_f_g)):
            if carga is not None and movimiento.unit != "kg":
                raise WodsValidationError(
                    message="Solo los movimientos medidos en kg admiten carga RX.",
                    field=f"movements.{indice}.load_rx_{lado}_g",
                )


_SEMANA: Final = re.compile(r"(\d{4})-W(\d{2})")


def week_dates(week: str) -> tuple[date, date]:
    """`AAAA-Www` (semana ISO) a (lunes, domingo), años 2020 a 2100. `WodsValidationError` con
    `field = "week"` si el formato, el año o la semana no existen."""
    coincide = _SEMANA.fullmatch(week)
    if coincide is not None:
        anio, semana = int(coincide.group(1)), int(coincide.group(2))
        if WEEK_MIN_YEAR <= anio <= WEEK_MAX_YEAR:
            try:
                lunes = date.fromisocalendar(anio, semana, 1)
            except ValueError:
                pass
            else:
                return lunes, date.fromisocalendar(anio, semana, 7)
    raise WodsValidationError(
        message="La semana debe tener el formato AAAA-Www (por ejemplo 2026-W43).", field="week"
    )
