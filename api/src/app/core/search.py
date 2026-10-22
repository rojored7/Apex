"""Utilidades de búsqueda compartidas por los services (revisión Python H3).

Antes cada módulo tenía su copia (`auth/rules`, `members/service`, `plans/service`) y la tabla
de tildes de socios y planes estaba incompleta (sin c-cedilla, a-diéresis ni e-circunfleja).

- `LIKE_ESCAPE` y `escape_like(value)`: escapa la barra invertida (primero), `%` y `_` para
  `ILIKE ... ESCAPE '\\'`; `contains_pattern(term)` da `%<term escapado>%`. El patrón viaja
  siempre como valor ligado, nunca como texto SQL.
- `strip_accents(value)` (Python): NFKD, sin marcas combinantes (categoría `Mn`) y en
  minúsculas (`casefold`).
- `sql_fold(expr)` (SQL): `translate(lower(expr), ACCENTED, PLAIN)`. La tabla trae también las
  mayúsculas: si el `LC_CTYPE` de la base no pliega `lower('Á')`, `translate` lo hace igual. Se
  aplica a la columna y al término, así comparan con la misma regla.
- `clean_query(q)`: NFC (una tilde combinada vale como la precompuesta), sin caracteres de
  control (`Cc`) y recortado. Defensa en profundidad: `SearchQuery` ya los rechaza con 422.

Solo importa SQLAlchemy y la biblioteca estándar; ningún módulo de negocio.
"""

from __future__ import annotations

import unicodedata
from typing import Final

from sqlalchemy import ColumnElement, func
from sqlalchemy.orm import InstrumentedAttribute

LIKE_ESCAPE: Final = "\\"
_MINUSCULAS: Final = "áéíóúüñàèìòùâêîôûäëïöç"


def strip_accents(value: str) -> str:
    """Pura: sin tildes ni diéresis y en minúsculas (`"Peña"` da `"pena"`)."""
    descompuesto = unicodedata.normalize("NFKD", value)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").casefold()


ACCENTED: Final = _MINUSCULAS + _MINUSCULAS.upper()
PLAIN: Final = "".join(strip_accents(c) for c in ACCENTED)


def escape_like(value: str) -> str:
    """Escapa la barra invertida (primero), `%` y `_` para `ILIKE ... ESCAPE`."""
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def contains_pattern(term: str) -> str:
    """`%<term escapado>%`, para `ILIKE` con `escape=LIKE_ESCAPE`."""
    return "%" + escape_like(term) + "%"


type TextExpr = ColumnElement[str] | InstrumentedAttribute[str]


def sql_fold(expr: TextExpr) -> ColumnElement[str]:
    """`translate(lower(expr), ACCENTED, PLAIN)`: el plegado de `strip_accents` en SQL."""
    return func.translate(func.lower(expr), ACCENTED, PLAIN)


def clean_query(q: str | None) -> str:
    """NFC, sin caracteres de control (`Cc`) y recortado; `None` da `""`."""
    sin_control = "".join(c for c in (q or "") if unicodedata.category(c) != "Cc")
    return unicodedata.normalize("NFC", sin_control).strip()
