"""Toda tabla de negocio declara `__audited__ = True` (US-024 T8; la completa US-107).

Exclusiones explícitas: `audit.audit_log` (es la cadena) y las tres tablas de `crypto`
(bitácora propia en `crypto_ops`). Los modelos de prueba (esquema `worker`, fuera de
`app.`) no cuentan.
"""

from __future__ import annotations

import importlib

from app.core.db import Base
from app.main import MODULES

EXCLUIDAS: dict[str, str] = {
    "audit.audit_log": "es la cadena de auditoría",
    "crypto.crypto_keys": "bitácora propia en crypto_ops",
    "crypto.crypto_ops": "bitácora propia",
    "crypto.crypto_jobs": "bitácora propia en crypto_ops",
    "auth.refresh_tokens": "rota cada 15 minutos; su ciclo lo registran los timestamps (US-041)",
}


def _cargar_modelos() -> None:
    importlib.import_module("app.core.audit")
    importlib.import_module("app.core.crypto.models")
    for nombre in MODULES:
        importlib.import_module(f"app.modules.{nombre}.models")


def _tablas_de_la_app() -> dict[str, type]:
    _cargar_modelos()
    salida: dict[str, type] = {}
    for mapper in Base.registry.mappers:
        clase = mapper.class_
        if not clase.__module__.startswith("app."):
            continue
        tabla = mapper.local_table
        nombre = f"{tabla.schema}.{tabla.name}" if tabla.schema else str(tabla.name)
        salida[nombre] = clase
    return salida


def test_las_exclusiones_existen() -> None:
    tablas = _tablas_de_la_app()
    assert set(EXCLUIDAS) <= set(tablas), sorted(set(EXCLUIDAS) - set(tablas))


def test_toda_tabla_no_excluida_esta_auditada() -> None:
    sin_auditar = sorted(
        nombre
        for nombre, clase in _tablas_de_la_app().items()
        if nombre not in EXCLUIDAS and not getattr(clase, "__audited__", False)
    )
    assert sin_auditar == []


def test_las_excluidas_no_declaran_audited() -> None:
    tablas = _tablas_de_la_app()
    con_audited = [n for n in EXCLUIDAS if getattr(tablas[n], "__audited__", False)]
    assert con_audited == []
