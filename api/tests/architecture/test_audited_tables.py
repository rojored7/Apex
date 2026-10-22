"""Toda tabla de negocio declara `__audited__ = True` (US-024 T8; la completa US-107 en S2-B6).

Exclusiones explícitas: `audit.audit_log` (es la cadena), las tres tablas de `crypto`
(bitácora propia en `crypto_ops`) y `auth.refresh_tokens`. Los modelos de prueba (esquema
`worker`, fuera de `app.`) no cuentan.

S2-B6 (decisión 21, riesgo 6.10): un módulo puede no tener `models.py` (`audit`, `dashboard`,
`tv`, `portal`), así que `_cargar_modelos()` importa `models` solo si `find_spec` lo encuentra.
`REQUIRED_AUDITED_TABLES_V01` deben existir y estar auditadas; las de `PENDING_AUDITED` todavía
pueden no existir, pero si ya existen y no declaran `__audited__ = True` la prueba falla. B7 y
B9 mueven su entrada de `PENDING_AUDITED` a `REQUIRED_AUDITED_TABLES_V01`.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Mapping
from importlib.util import find_spec

import pytest

from app.core.db import Base
from app.main import MODULES

EXCLUIDAS: dict[str, str] = {
    "audit.audit_log": "es la cadena de auditoría",
    "crypto.crypto_keys": "bitácora propia en crypto_ops",
    "crypto.crypto_ops": "bitácora propia",
    "crypto.crypto_jobs": "bitácora propia en crypto_ops",
    "auth.refresh_tokens": "rota cada 15 minutos; su ciclo lo registran los timestamps (US-041)",
}

REQUIRED_AUDITED_TABLES_V01: frozenset[str] = frozenset(
    {"auth.users", "auth.one_time_tokens", "settings.settings_sections"}
)
PENDING_AUDITED: dict[str, str] = {
    "members.members": "B7",
    "plans.plans": "B9",
    "memberships.memberships": "Sprint 3",
    "payments.payments": "Sprint 3",
}


def _cargar_modelos(modulos: Iterable[str] = MODULES) -> None:
    importlib.import_module("app.core.audit")
    importlib.import_module("app.core.crypto.models")
    for nombre in modulos:
        ruta = f"app.modules.{nombre}.models"
        if find_spec(ruta) is not None:
            importlib.import_module(ruta)


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


def _incumplidas(tablas: Mapping[str, type]) -> list[str]:
    """Requeridas ausentes o sin auditar, y pendientes que ya existen sin auditar."""
    faltan = [f"{n}: no existe" for n in sorted(REQUIRED_AUDITED_TABLES_V01 - set(tablas))]
    sin_auditar = [
        f"{n}: sin __audited__ = True"
        for n in sorted(REQUIRED_AUDITED_TABLES_V01 | set(PENDING_AUDITED))
        if n in tablas and not getattr(tablas[n], "__audited__", False)
    ]
    return faltan + sin_auditar


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


def test_las_requeridas_de_v01_existen_y_las_pendientes_presentes_estan_auditadas() -> None:
    assert _incumplidas(_tablas_de_la_app()) == []


def test_requeridas_y_pendientes_no_se_solapan_ni_estan_excluidas() -> None:
    assert not REQUIRED_AUDITED_TABLES_V01 & set(PENDING_AUDITED)
    assert not (REQUIRED_AUDITED_TABLES_V01 | set(PENDING_AUDITED)) & set(EXCLUIDAS)


class _Auditada:
    __audited__ = True


class _SinAuditar:
    pass


def _requeridas_auditadas() -> dict[str, type]:
    return dict.fromkeys(REQUIRED_AUDITED_TABLES_V01, _Auditada)


@pytest.mark.parametrize("pendiente", sorted(PENDING_AUDITED))
def test_una_pendiente_que_ya_existe_sin_audited_falla(pendiente: str) -> None:
    tablas = {**_requeridas_auditadas(), pendiente: _SinAuditar}
    assert _incumplidas(tablas) == [f"{pendiente}: sin __audited__ = True"]


def test_una_pendiente_que_no_existe_no_falla() -> None:
    assert _incumplidas(_requeridas_auditadas()) == []


def test_una_pendiente_que_existe_auditada_no_falla() -> None:
    assert _incumplidas({**_requeridas_auditadas(), "members.members": _Auditada}) == []


def test_una_requerida_ausente_o_sin_audited_falla() -> None:
    tablas: dict[str, type] = {**_requeridas_auditadas(), "auth.users": _SinAuditar}
    del tablas["settings.settings_sections"]
    assert _incumplidas(tablas) == [
        "settings.settings_sections: no existe",
        "auth.users: sin __audited__ = True",
    ]


def test_cargar_modelos_tolera_un_modulo_sin_models() -> None:
    """Decisión 21: `audit` no tiene `models.py` (sus models viven en `core/audit.py`)."""
    assert find_spec("app.modules.audit.models") is None
    _cargar_modelos(("auth", "settings", "audit"))
