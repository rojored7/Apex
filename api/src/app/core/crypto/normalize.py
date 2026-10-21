"""Normalización del índice ciego (US-026 T1; N-02). **Irreversible con datos** (ADR-002).

- `generic` (documento): NFKD, sin marcas diacríticas (categoría `Mn`), minúsculas con
  `lower()` (no `casefold()`, que expande `ß`), sin espacios en blanco Unicode (incluye
  tabulador y espacio no separable), sin puntos ni guiones (`-` y los tipográficos).
- `phone`: solo dígitos ASCII; se quita el `57` inicial únicamente si quedan 12 dígitos
  (código de país más un número colombiano de 10), para no recortar números sin prefijo.
- `email`: minúsculas y sin espacios en blanco; conserva puntos, guiones y tildes.
Un resultado vacío lanza `CryptoError("empty_value")` sin incluir el valor.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final, Literal

from app.core.crypto.errors import CryptoError

IndexKind = Literal["generic", "phone", "email"]

_ESPACIOS: Final = re.compile(r"\s+")
_GUIONES: Final = "-" + "".join(map(chr, range(0x2010, 0x2016)))  # guiones tipográficos
_PUNTOS_Y_GUIONES: Final = re.compile("[." + re.escape(_GUIONES) + "]")
_DIGITOS: Final = frozenset("0123456789")
_PREFIJO_PAIS: Final = "57"
_LARGO_CON_PREFIJO: Final = 12


def _generic(value: str) -> str:
    sin_marcas = "".join(
        c for c in unicodedata.normalize("NFKD", value) if unicodedata.category(c) != "Mn"
    )
    return _PUNTOS_Y_GUIONES.sub("", _ESPACIOS.sub("", sin_marcas.lower()))


def _phone(value: str) -> str:
    digitos = "".join(c for c in value if c in _DIGITOS)
    if len(digitos) == _LARGO_CON_PREFIJO and digitos.startswith(_PREFIJO_PAIS):
        return digitos[len(_PREFIJO_PAIS) :]
    return digitos


def _email(value: str) -> str:
    return _ESPACIOS.sub("", value.lower())


def normalize_for_index(value: str, kind: IndexKind) -> str:
    if kind == "generic":
        salida = _generic(value)
    elif kind == "phone":
        salida = _phone(value)
    elif kind == "email":
        salida = _email(value)
    else:
        raise CryptoError("unsupported", f"tipo de índice desconocido: {kind}")
    if not salida:
        raise CryptoError("empty_value", "valor vacío tras normalizar para el índice ciego")
    return salida
