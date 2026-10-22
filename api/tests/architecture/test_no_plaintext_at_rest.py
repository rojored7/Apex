"""Ninguna columna cifrada de la app guarda claro (S2-B7; US-031 criterio 4; CLAUDE.md bus 7 y 9).

- Las columnas cifradas se descubren solas: toda columna de `Base.metadata` cuyo tipo expone
  `is_encrypted`, solo de modelos cuyo módulo empieza por `app.` (el modelo de prueba de
  `tests/crypto/models_fixture.py` no cuenta). Se cargan los `models.py` de todos los paquetes
  de `app.modules`, estén o no en `MODULES`.
- Toda tabla con columnas cifradas tiene fábrica en `tests/factories.FACTORIES`; con ella se crea
  una fila y, por SQL crudo, cada columna cifrada es nula o un blob `apx1.<uuid>.A256GCM.` y la
  fila no contiene ningún valor de `KNOWN` en claro ni normalizado.
- `test_registry_columns_are_encrypted`: cada columna de `registry` (`esquema.tabla.columna`)
  existe como `Encrypted` de su `data_class`; cada clase con índice ciego tiene su `BlindIndexed`
  con `source` en esa columna. Una tabla aún inexistente avisa (`UserWarning`); las de v0.1 que
  ya deben existir (`members.members`) son error.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import warnings
from importlib.util import find_spec
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules
from app.core.crypto.keyring import Keyring
from app.core.crypto.registry import encrypting_specs, indexing_specs
from app.core.crypto.types import BlindIndexed, Encrypted
from app.core.db import Base
from tests.factories import FACTORIES
from tests.factories.members import KNOWN_NORMALIZED

BLOB = re.compile(r"^apx1\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.A256GCM\.")
# Tablas del registro que en v0.1 ya deben existir como modelo (S2-B7).
TABLAS_OBLIGATORIAS_V01: frozenset[str] = frozenset({"members.members"})


def _cargar_todos_los_modelos() -> None:
    for modulo in pkgutil.iter_modules(app.modules.__path__):
        ruta = f"app.modules.{modulo.name}.models"
        if modulo.ispkg and find_spec(ruta) is not None:
            importlib.import_module(ruta)


def _columnas_de_la_app() -> dict[str, dict[str, Any]]:
    """`{esquema.tabla: {columna: Column}}` de los modelos de `app.`."""
    _cargar_todos_los_modelos()
    salida: dict[str, dict[str, Any]] = {}
    for mapper in Base.registry.mappers:
        if not mapper.class_.__module__.startswith("app."):
            continue
        tabla: Any = mapper.local_table
        nombre = f"{tabla.schema}.{tabla.name}" if tabla.schema else str(tabla.name)
        salida[nombre] = {c.name: c for c in tabla.columns}
    return salida


def _cifradas() -> dict[str, list[str]]:
    return {
        tabla: sorted(n for n, c in columnas.items() if getattr(c.type, "is_encrypted", False))
        for tabla, columnas in _columnas_de_la_app().items()
        if any(getattr(c.type, "is_encrypted", False) for c in columnas.values())
    }


def test_descubre_las_cinco_columnas_cifradas_de_socios() -> None:
    cifradas = _cifradas()
    assert cifradas.get("members.members") == [
        "birth_date",
        "document",
        "email",
        "emergency_contact",
        "phone",
    ]


def test_el_modelo_de_prueba_del_bus_no_cuenta() -> None:
    importlib.import_module("tests.crypto.models_fixture")
    assert not any(t.startswith("test_crypto.") for t in _cifradas())


def test_toda_tabla_con_columnas_cifradas_tiene_fabrica() -> None:
    faltan = [
        f"agregue una fábrica para {tabla}" for tabla in _cifradas() if tabla not in FACTORIES
    ]
    assert faltan == []


async def test_ninguna_columna_cifrada_guarda_claro(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    cifradas = _cifradas()
    assert cifradas, "no se descubrió ninguna columna cifrada"
    for tabla, columnas in cifradas.items():
        fila = await FACTORIES[tabla](session)
        valores = (
            (
                await session.execute(
                    text(f"SELECT {', '.join(columnas)} FROM {tabla} WHERE id = :id"),  # noqa: S608
                    {"id": fila.id},
                )
            )
            .mappings()
            .one()
        )
        for columna in columnas:
            valor = valores[columna]
            assert valor is None or BLOB.match(valor), f"{tabla}.{columna}"
        json_texto = await session.scalar(
            text(f"SELECT row_to_json(t)::text FROM {tabla} t WHERE t.id = :id"),  # noqa: S608
            {"id": fila.id},
        )
        for conocido in KNOWN_NORMALIZED:
            assert conocido not in (json_texto or ""), f"{tabla}: {conocido}"


def test_registry_columns_are_encrypted() -> None:
    tablas = _columnas_de_la_app()
    errores: list[str] = []
    for spec in encrypting_specs():
        for ruta in spec.columns:
            esquema, tabla, columna = ruta.split(".")
            nombre = f"{esquema}.{tabla}"
            if nombre not in tablas:
                if nombre in TABLAS_OBLIGATORIAS_V01:
                    errores.append(f"{ruta}: la tabla {nombre} no tiene modelo")
                else:
                    warnings.warn(
                        f"{ruta}: la tabla {nombre} aún no existe", UserWarning, stacklevel=1
                    )
                continue
            col = tablas[nombre].get(columna)
            if col is None or not isinstance(col.type, Encrypted):
                errores.append(f"{ruta}: no es Encrypted")
            elif col.type.data_class != spec.name:
                errores.append(f"{ruta}: data_class {col.type.data_class} en vez de {spec.name}")
    indices = {s.name for s in indexing_specs()}
    for spec in encrypting_specs():
        if spec.name not in indices:
            continue
        for ruta in spec.columns:
            esquema, tabla, columna = ruta.split(".")
            columnas = tablas.get(f"{esquema}.{tabla}", {})
            if not columnas:
                continue
            con_indice = [
                c
                for c in columnas.values()
                if isinstance(c.type, BlindIndexed)
                and c.type.source == columna
                and c.type.data_class == spec.name
            ]
            if not con_indice:
                errores.append(f"{ruta}: falta su BlindIndexed")
    assert errores == []


def test_las_tablas_obligatorias_estan_en_el_registro() -> None:
    del_registro = {".".join(r.split(".")[:2]) for s in encrypting_specs() for r in s.columns}
    assert del_registro >= TABLAS_OBLIGATORIAS_V01
