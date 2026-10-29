"""Diff y marcador de blobs del detalle de auditoría (S4A-B4, US-103; S4A-D17, S4A-D18, S4A-D52).

Privado de `audit` (`PRIVATE_HELPERS["audit"]`); funciones puras, sin base ni bus de cifrado (el
módulo no importa `core.crypto`: parte el texto según el formato de `CLAUDE.md`, y una prueba fija
la paridad del prefijo y del separador con `core/crypto`).

- `blob_marker(value)`: para un texto `apx1.<key_id>.<alg>.<nonce>.<ct>` (cinco partes separadas
  por `BLOB_SEPARATOR`, `key_id` UUID, `alg` no vacío) devuelve `{"encrypted": True, "key_id":
  "<uuid en minúsculas>", "alg": "<alg>"}`; cualquier otra cosa (texto sin el prefijo, blob mal
  formado, no texto) da `None`.
- `redact_blobs(mapping)`: copia del diccionario con cada blob sustituido por su marcador, también
  dentro de diccionarios y listas anidados; `None` da `None`. Nunca muta la entrada. Un texto que
  contiene `apx1.` en cualquier posición y no es un blob bien formado desde el inicio tampoco sale
  tal cual: va como `MALFORMED_BLOB_MARKER` (`key_id` y `alg` nulos) y su `FieldChange.encrypted`
  es verdadero (S4A-D105, revisión de B4). Más allá de `MAX_DEPTH` (32) niveles el valor sale
  como `TRUNCATED_MARKER` (`{"truncated": true}`), nunca un `RecursionError`.
- `diff(before, after, action)`: lista de `FieldChange` ordenada por nombre de campo. `insert`
  (o `before` nulo): todo `added`; `delete` (o `after` nulo): todo `removed`; `update`: solo los
  campos distintos (`changed`; `added`/`removed` si el campo falta de un lado), un `update` sin
  cambios da `[]`; en las lecturas (`reveal`, `login`, `verify`, `download`, `export`) se ignora
  `before` y todo `after` es `added`. `encrypted` es verdadero si el valor de antes o de después
  es un blob; los valores salen ya con el marcador.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from app.modules.audit.schemas import ChangeKind, FieldChange

__all__ = [
    "BLOB_PARTS",
    "BLOB_PREFIX",
    "BLOB_SEPARATOR",
    "MALFORMED_BLOB_MARKER",
    "MAX_DEPTH",
    "READ_ACTIONS",
    "TRUNCATED_MARKER",
    "FieldChange",
    "blob_marker",
    "diff",
    "redact_blobs",
]

BLOB_SEPARATOR: Final = "."
BLOB_PREFIX: Final = "apx1" + BLOB_SEPARATOR
BLOB_PARTS: Final = 5
READ_ACTIONS: Final[frozenset[str]] = frozenset({"reveal", "login", "verify", "download", "export"})
MALFORMED_BLOB_MARKER: Final[Mapping[str, Any]] = MappingProxyType(
    {"encrypted": True, "key_id": None, "alg": None}
)
"""Marcador de un texto que contiene `apx1.` (en cualquier posición) y no es un blob bien formado
desde el inicio (S4A-D105; revisión de B4, L): por seguridad tampoco sale tal cual."""
MAX_DEPTH: Final = 32
"""Profundidad máxima que recorren `redact_blobs` y `diff` (revisión de B4, L): más abajo, el
valor se sustituye por `TRUNCATED_MARKER` en vez de agotar la pila (500)."""
TRUNCATED_MARKER: Final[Mapping[str, Any]] = MappingProxyType({"truncated": True})
FIELD_DEPTH: Final = 2
"""Nivel de un campo de `before`/`after` (el diccionario de la fila es el nivel 1)."""
_TOKEN: Final = re.compile(r"[A-Za-z0-9_-]+")
"""`alg`, nonce y cifrado de un blob bien formado: no vacíos y en base64url (`fullmatch`, así un
salto de línea final no pasa)."""


def blob_marker(value: object) -> dict[str, Any] | None:
    """El marcador `{"encrypted", "key_id", "alg"}` de un blob `apx1.`; si no lo es, `None`."""
    if not isinstance(value, str) or not value.startswith(BLOB_PREFIX):
        return None
    partes = value.split(BLOB_SEPARATOR)
    if len(partes) != BLOB_PARTS:
        return None
    _, key_id, alg, nonce, cifrado = partes
    if not all(_TOKEN.fullmatch(parte) for parte in (alg, nonce, cifrado)):
        return None  # vacío o con espacios, saltos u otros caracteres fuera de base64url
    try:
        llave = UUID(key_id)
    except ValueError:
        return None
    return {"encrypted": True, "key_id": str(llave), "alg": alg}


def _is_blob_like(value: object) -> bool:
    """Todo texto que contiene `apx1.` en cualquier posición (con espacios o saltos delante,
    incrustado o mal formado; S4A-D105 y revisión de B4)."""
    return isinstance(value, str) and BLOB_PREFIX in value


def _redact_value(value: Any, depth: int) -> Any:
    """El valor con cada blob sustituido; recursivo en diccionarios y listas hasta `MAX_DEPTH`,
    sin mutar."""
    if depth > MAX_DEPTH:
        return dict(TRUNCATED_MARKER)
    if _is_blob_like(value):
        return blob_marker(value) or dict(MALFORMED_BLOB_MARKER)
    if isinstance(value, Mapping):
        return {clave: _redact_value(interno, depth + 1) for clave, interno in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(interno, depth + 1) for interno in value]
    return value


def redact_blobs(mapping: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Copia de `mapping` con cada blob (también anidado) sustituido por su marcador."""
    if mapping is None:
        return None
    return {clave: _redact_value(valor, FIELD_DEPTH) for clave, valor in mapping.items()}


def _change(field: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> FieldChange | None:
    """El cambio de un campo (comparado en crudo: dos blobs distintos de la misma llave son un
    cambio aunque sus marcadores coincidan); `None` si el valor no cambió."""
    antes, despues = before.get(field), after.get(field)
    if field not in before:
        kind: ChangeKind = "added"
    elif field not in after:
        kind = "removed"
    elif antes == despues:
        return None
    else:
        kind = "changed"
    return FieldChange(
        field=field,
        kind=kind,
        before=_redact_value(antes, FIELD_DEPTH),
        after=_redact_value(despues, FIELD_DEPTH),
        encrypted=_contains_blob(antes, FIELD_DEPTH) or _contains_blob(despues, FIELD_DEPTH),
    )


def _contains_blob(value: Any, depth: int) -> bool:
    """Si hay un blob hasta `MAX_DEPTH`; lo de más abajo sale truncado, sin datos."""
    if depth > MAX_DEPTH:
        return False
    if _is_blob_like(value):
        return True
    if isinstance(value, Mapping):
        return any(_contains_blob(interno, depth + 1) for interno in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_blob(interno, depth + 1) for interno in value)
    return False


def diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, action: str
) -> list[FieldChange]:
    """Cambios campo a campo, ordenados por nombre (ver el docstring del módulo)."""
    antes: Mapping[str, Any] = {} if before is None or action in READ_ACTIONS else before
    despues: Mapping[str, Any] = {} if after is None else after
    cambios = (_change(campo, antes, despues) for campo in sorted({*antes, *despues}))
    return [cambio for cambio in cambios if cambio is not None]
