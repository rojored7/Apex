"""Registro de clases de dato (US-025 T1; N-04). Constante en código, no tabla.

`data_class` decide la llave; quien llama al bus nunca elige llave ni algoritmo. Cada
entrada declara si se cifra, el tipo de normalización del índice ciego (N-02), si se firma,
el tipo del valor y las columnas `esquema.tabla.columna` que la usan (texto, sin importar
modelos de ningún módulo: lo verifican US-030 y US-031).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from app.core.crypto.errors import CryptoError

IndexKind = Literal["generic", "phone", "email"]
ValueType = Literal["str", "date", "json"]


@dataclass(frozen=True)
class DataClassSpec:
    name: str
    encrypt: bool
    index_kind: IndexKind | None
    sign: bool
    value_type: ValueType
    columns: tuple[str, ...]


_V01: tuple[DataClassSpec, ...] = (
    DataClassSpec("member.document", True, "generic", False, "str", ("members.members.document",)),
    DataClassSpec("member.phone", True, "phone", False, "str", ("members.members.phone",)),
    DataClassSpec("member.email", True, "email", False, "str", ("members.members.email",)),
    DataClassSpec("member.birth_date", True, None, False, "date", ("members.members.birth_date",)),
    DataClassSpec(
        "member.emergency_contact",
        True,
        None,
        False,
        "json",
        ("members.members.emergency_contact",),
    ),
)

REGISTRY: Mapping[str, DataClassSpec] = {spec.name: spec for spec in _V01}

_active: Mapping[str, DataClassSpec] = REGISTRY


def get_spec(name: str) -> DataClassSpec:
    try:
        return _active[name]
    except KeyError:
        raise CryptoError("unknown_data_class", f"data_class desconocida: {name}") from None


def encrypting_specs() -> list[DataClassSpec]:
    return [s for s in _active.values() if s.encrypt]


def indexing_specs() -> list[DataClassSpec]:
    return [s for s in _active.values() if s.index_kind is not None]


def signing_specs() -> list[DataClassSpec]:
    return [s for s in _active.values() if s.sign]


@contextmanager
def override_registry(specs: Mapping[str, DataClassSpec]) -> Iterator[None]:
    """Solo para pruebas: sustituye el registro dentro del bloque."""
    global _active
    anterior = _active
    _active = dict(specs)
    try:
        yield
    finally:
        _active = anterior
