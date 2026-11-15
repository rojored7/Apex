"""Reglas puras de `wods` (S8-A1, US-165; S8-D5). Sin sesión ni reloj: se prueban sin base.

- `normalize_movement_name(name)`: NFKC, recorte, espacios internos colapsados y minúsculas; es la
  clave de unicidad del catálogo (`name_norm`). Si queda vacío o pasa de 60 caracteres (NFKC puede
  expandir), `WodsValidationError` con `field = "name"` y sin repetir el valor.
"""

from __future__ import annotations

import re
import unicodedata
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
