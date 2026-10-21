"""`Secret`: valor sensible opaco con dos estados (US-028 T2, T8).

- `Secret.from_plain(valor)`: pendiente; el listener de `types.py` lo cifra en el flush.
- `Secret.from_blob(blob)`: sellado; es lo que vuelve de la base y lo único que el
  `TypeDecorator` deja escribir.
- Nunca muestra su contenido: `repr`, `str`, `json.dumps`, `pickle` y la serialización de
  Pydantic fallan o devuelven `Secret(•••)`. Leer en claro exige `types.reveal(...)` con un
  propósito, que deja rastro en `crypto_ops`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any

PlainValue = str | date | Mapping[str, Any]
_MASK = "Secret(•••)"


def canonical_json(value: Mapping[str, object]) -> str:
    """JSON con llaves ordenadas y separadores compactos; lo que se cifra para `json`."""
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Secret:
    __slots__ = ("_blob", "_plain")

    def __init__(self, *, plain: PlainValue | None, blob: str | None) -> None:
        self._plain = plain
        self._blob = blob

    @classmethod
    def from_plain(cls, value: PlainValue) -> Secret:
        if not isinstance(value, str | date | Mapping):
            raise TypeError("Secret.from_plain acepta str, date o un mapeo")
        return cls(plain=value, blob=None)

    @classmethod
    def from_blob(cls, blob: str) -> Secret:
        return cls(plain=None, blob=blob)

    @property
    def is_sealed(self) -> bool:
        return self._blob is not None

    @property
    def blob(self) -> str:
        if self._blob is None:
            raise ValueError("el Secret no está sellado todavía (se cifra en el flush)")
        return self._blob

    def _take_plain(self) -> PlainValue:
        """Solo para el listener de cifrado de `types.py`."""
        if self._plain is None:
            raise ValueError("el Secret ya está sellado")
        return self._plain

    def __repr__(self) -> str:
        return _MASK

    def __str__(self) -> str:
        return _MASK

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        return self._blob is not None and self._blob == other._blob

    def __hash__(self) -> int:
        return hash(self._blob)

    def __reduce__(self) -> str | tuple[Any, ...]:
        raise TypeError("Secret no se serializa (pickle)")

    def __json__(self) -> None:
        raise TypeError("Secret no se serializa (json)")

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
        from pydantic_core import core_schema

        def _no(value: Any, info: Any) -> Any:
            raise TypeError("Secret no se serializa: use reveal(obj, campo, proposito)")

        return core_schema.is_instance_schema(
            cls,
            serialization=core_schema.plain_serializer_function_ser_schema(_no, info_arg=True),
        )
