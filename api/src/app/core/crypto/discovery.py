"""Descubrimiento de las columnas `Encrypted` de una clase (S4B-B3b, US-030; S4B-D39).

`encrypted_columns(metadata, data_class)` recorre `registry.get_spec(data_class).columns` (texto
`esquema.tabla.columna`), las busca en `metadata.tables` y devuelve una `ColumnRef` por columna.
Excluye el esquema `audit` (sus blobs los cuenta `retire-key`, no los recifra la rotación). Lanza
`ValueError` si una columna del registro no existe en `metadata` o no es un `Encrypted` de esa
clase, y `CryptoError(unknown_data_class)` si la clase no está en el registro. No nombra modelos
de ningún módulo ni importa `app.modules` (`tests/architecture/test_guarded_calls.py`): trabaja
sobre `Table` de Core, así que el llamador debe haber cargado los services (`load_module_services`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Column, MetaData, Table

from app.core.crypto.registry import get_spec
from app.core.crypto.types import Encrypted

AUDIT_SCHEMA = "audit"


@dataclass(frozen=True)
class ColumnRef:
    """Una columna cifrada: su tabla de Core y el nombre de la columna."""

    table: Table
    name: str

    @property
    def qualified(self) -> str:
        """`esquema.tabla.columna`, el texto del registro."""
        return f"{self.table.schema}.{self.table.name}.{self.name}"

    @property
    def column(self) -> Column[object]:
        return self.table.c[self.name]


def _resolve(metadata: MetaData, qualified: str, data_class: str) -> ColumnRef:
    """`ColumnRef` de un texto del registro; `ValueError` si no es un `Encrypted` de la clase."""
    esquema, _, resto = qualified.partition(".")
    tabla_nombre, _, columna = resto.partition(".")
    tabla = metadata.tables.get(f"{esquema}.{tabla_nombre}")
    if tabla is None:
        raise ValueError(f"la tabla {esquema}.{tabla_nombre} del registro no está en el metadata")
    if columna not in tabla.c:
        raise ValueError(f"la columna {qualified} del registro no existe")
    tipo = tabla.c[columna].type
    if not isinstance(tipo, Encrypted) or tipo.data_class != data_class:
        raise ValueError(f"la columna {qualified} no es un Encrypted de {data_class}")
    return ColumnRef(tabla, columna)


def encrypted_columns(metadata: MetaData, data_class: str) -> list[ColumnRef]:
    """Las columnas `Encrypted(data_class)` de `metadata` que el registro declara para la clase."""
    spec = get_spec(data_class)
    return [
        _resolve(metadata, texto, data_class)
        for texto in spec.columns
        if texto.partition(".")[0] != AUDIT_SCHEMA
    ]
