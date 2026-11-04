"""`encrypted_columns(metadata, data_class)`: las columnas `Encrypted` de una clase (S4B-B3b; D39).

Contrato: cruza `registry.get_spec(clase).columns` (`esquema.tabla.columna`) con `metadata`,
excluye el esquema `audit` y lanza `ValueError` si una columna del registro no existe o no es un
`Encrypted` de esa clase. `kek.backup` (sin llave ni columnas) da lista vacía; una clase fuera
del registro lanza `CryptoError(unknown_data_class)`.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Column, MetaData, Table, Text, Uuid

from app.core.crypto.discovery import ColumnRef, encrypted_columns
from app.core.crypto.errors import CryptoError
from app.core.crypto.registry import REGISTRY, DataClassSpec, override_registry
from app.core.crypto.types import Encrypted
from app.core.db import Base
from app.main import load_module_services

CLASE = "member.document"


def _registro(*columnas: str) -> dict[str, DataClassSpec]:
    return {**REGISTRY, CLASE: replace(REGISTRY[CLASE], columns=tuple(columnas))}


def _tabla(
    metadata: MetaData, esquema: str, nombre: str, tipo: object, columna: str = "doc"
) -> Table:
    return Table(
        nombre,
        metadata,
        Column("id", Uuid, primary_key=True),
        Column(columna, tipo),
        schema=esquema,
    )  # type: ignore[arg-type]


def test_ve_members_members_document_tras_cargar_los_services() -> None:
    load_module_services()

    columnas = encrypted_columns(Base.metadata, CLASE)

    assert [c.qualified for c in columnas] == ["members.members.document"]
    assert isinstance(columnas[0], ColumnRef)
    assert columnas[0].table.name == "members"
    assert columnas[0].name == "document"


def test_cada_clase_de_socio_apunta_a_su_columna() -> None:
    load_module_services()

    visto = {
        clase: [c.qualified for c in encrypted_columns(Base.metadata, clase)]
        for clase in (
            "member.phone",
            "member.email",
            "member.birth_date",
            "member.emergency_contact",
        )
    }

    assert visto == {
        "member.phone": ["members.members.phone"],
        "member.email": ["members.members.email"],
        "member.birth_date": ["members.members.birth_date"],
        "member.emergency_contact": ["members.members.emergency_contact"],
    }


def test_excluye_el_esquema_audit() -> None:
    metadata = MetaData()
    _tabla(metadata, "demo", "personas", Encrypted(CLASE))
    _tabla(metadata, "audit", "copia", Encrypted(CLASE))
    with override_registry(_registro("demo.personas.doc", "audit.copia.doc")):
        columnas = encrypted_columns(metadata, CLASE)

    assert [c.qualified for c in columnas] == ["demo.personas.doc"]


def test_falla_si_la_columna_no_es_encrypted() -> None:
    metadata = MetaData()
    _tabla(metadata, "demo", "personas", Text())
    with override_registry(_registro("demo.personas.doc")), pytest.raises(ValueError):
        encrypted_columns(metadata, CLASE)


def test_falla_si_la_columna_es_encrypted_de_otra_clase() -> None:
    metadata = MetaData()
    _tabla(metadata, "demo", "personas", Encrypted("member.phone"))
    with override_registry(_registro("demo.personas.doc")), pytest.raises(ValueError):
        encrypted_columns(metadata, CLASE)


def test_falla_si_la_columna_del_registro_no_existe() -> None:
    metadata = MetaData()
    _tabla(metadata, "demo", "personas", Encrypted(CLASE), columna="otra")
    with override_registry(_registro("demo.personas.doc")), pytest.raises(ValueError):
        encrypted_columns(metadata, CLASE)


def test_falla_si_la_tabla_del_registro_no_existe() -> None:
    with override_registry(_registro("demo.fantasma.doc")), pytest.raises(ValueError):
        encrypted_columns(MetaData(), CLASE)


def test_kek_backup_no_tiene_columnas() -> None:
    load_module_services()

    assert encrypted_columns(Base.metadata, "kek.backup") == []


def test_una_clase_fuera_del_registro_lanza_unknown_data_class() -> None:
    with pytest.raises(CryptoError) as error:
        encrypted_columns(Base.metadata, "attachment.sensitive")

    assert error.value.code == "unknown_data_class"
