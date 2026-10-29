"""Toda tabla de negocio declara `__audited__ = True` (US-024 T8; la completa US-107 en S2-B6).

Exclusiones explícitas: `audit.audit_log` (es la cadena), las tres tablas de `crypto`
(bitácora propia en `crypto_ops`), `auth.refresh_tokens` y `worker.job_runs` (bitácora operativa del
worker, S4A-D3; `_cargar_modelos` importa `app.core.jobs`) y `audit.verifications` (su resultado
entra a la cadena como fila `verify`, S4A-D12; `_cargar_modelos` importa `app.core.audit_verify`).
Los modelos de prueba (esquema `worker`, fuera de `app.`) no cuentan.

S2-B6 (decisión 21, riesgo 6.10): un módulo puede no tener `models.py` (`audit`, `dashboard`,
`tv`, `portal`), así que `_cargar_modelos()` importa `models` solo si `find_spec` lo encuentra.
`REQUIRED_AUDITED_TABLES_V01` deben existir y estar auditadas; las de `PENDING_AUDITED` todavía
pueden no existir, pero si ya existen y no declaran `__audited__ = True` la prueba falla. B7 y
B9 mueven su entrada de `PENDING_AUDITED` a `REQUIRED_AUDITED_TABLES_V01` (S2-B7: `members.members`,
con `members` en `MODULES`; S2-B9: `plans.plans`, con `plans` en `MODULES`). S3-B1 mueve
`memberships.memberships` (con `__audit_subject__ = "member_id"`, G-05); S3-B2 mueve
`memberships.membership_freezes` (sin `__audit_subject__`: la tabla no tiene `member_id`; la fila
`update` de la membresía lleva el socio; anotado para US-106) y S3-B3 mueve `payments.payments`
(con `__audit_subject__ = "member_id"`, G-05).
`PENDING_AUDITED` conserva entradas futuras (`classes.class_sessions`,
`notifications.notifications`) para no dejar vacía la parametrización.
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
    "worker.job_runs": "bitácora operativa del worker; no se audita (US-113, S4A-D3)",
    "audit.verifications": "su resultado entra a la cadena como fila verify (N-30, S4A-D12)",
}

REQUIRED_AUDITED_TABLES_V01: frozenset[str] = frozenset(
    {
        "auth.users",
        "auth.one_time_tokens",
        "settings.settings_sections",
        "members.members",
        "plans.plans",
        "memberships.memberships",
        "memberships.membership_freezes",
        "payments.payments",
    }
)
PENDING_AUDITED: dict[str, str] = {
    "classes.class_sessions": "Sprint 7",
    "notifications.notifications": "Sprint 5",
}


def _cargar_modelos(modulos: Iterable[str] = MODULES) -> None:
    importlib.import_module("app.core.audit")
    importlib.import_module("app.core.crypto.models")
    importlib.import_module("app.core.jobs")  # S4A-B1: `worker.job_runs` (S4A-D3)
    importlib.import_module("app.core.audit_verify")  # S4A-B3: `audit.verifications` (S4A-D12)
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
    tablas = {**_requeridas_auditadas(), "classes.class_sessions": _Auditada}
    assert _incumplidas(tablas) == []


def test_members_es_requerida_y_declara_su_sujeto() -> None:
    """S2-B7: `members.members` es requerida y declara `__audit_subject__ = "id"` (llena
    `subject_member_id`). Que `members` esté en `MODULES` lo exige `test_audit_module.py`."""
    assert "members.members" in REQUIRED_AUDITED_TABLES_V01
    _cargar_modelos(("members",))
    tablas = _tablas_de_la_app()
    assert "members.members" in tablas
    assert getattr(tablas["members.members"], "__audit_subject__", None) == "id"


def test_plans_es_requerida_y_su_modulo_esta_en_modules() -> None:
    """S2-B9: `plans.plans` es requerida y se descubre desde `MODULES` (no por el import de una
    prueba): con `plans` fuera de `MODULES` la tabla no existiría en una corrida aislada."""
    assert "plans.plans" in REQUIRED_AUDITED_TABLES_V01
    assert "plans.plans" not in PENDING_AUDITED
    assert "plans" in MODULES
    _cargar_modelos(("plans",))
    tablas = _tablas_de_la_app()
    assert getattr(tablas["plans.plans"], "__audited__", False) is True


def test_membership_y_payment_declaran_sujeto() -> None:
    """S3-B1 y S3-B3 (G-05): `memberships.memberships` y `payments.payments` son requeridas, sus
    módulos están en `MODULES` y declaran `__audit_subject__ = "member_id"` (la fila de auditoría
    lleva el socio)."""
    tablas = _tablas_de_la_app()
    for tabla, modulo in (
        ("memberships.memberships", "memberships"),
        ("payments.payments", "payments"),
    ):
        assert tabla in REQUIRED_AUDITED_TABLES_V01
        assert tabla not in PENDING_AUDITED
        assert modulo in MODULES
        clase = tablas[tabla]
        assert getattr(clase, "__audited__", False) is True, tabla
        assert getattr(clase, "__audit_subject__", None) == "member_id", tabla


def test_membership_freezes_es_requerida_y_no_declara_sujeto_por_decision_s4a_d20() -> None:
    """S3-B2 (D14): `memberships.membership_freezes` es requerida y auditada. S4A-D20 (US-106):
    no declara `__audit_subject__` y no se le agrega, porque necesitaría `member_id`, una columna
    nueva en una tabla append-only con trigger (el relleno con `UPDATE` está bloqueado). La
    congelación aparece en el historial del socio por la fila `update` de
    `memberships.memberships` (`end_date` y `status`), que sí lleva el socio."""
    assert "memberships.membership_freezes" in REQUIRED_AUDITED_TABLES_V01
    assert "memberships.membership_freezes" not in PENDING_AUDITED
    tablas = _tablas_de_la_app()
    congelacion = tablas["memberships.membership_freezes"]
    assert getattr(congelacion, "__audited__", False) is True
    assert getattr(congelacion, "__audit_subject__", None) is None


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
