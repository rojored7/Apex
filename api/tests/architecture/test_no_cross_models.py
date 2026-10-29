"""Ningún módulo importa `models` ni `router` ajenos (US-022 T4; reglas de módulos 1 y 2).

S3-B1 (D7, US-084): la prueba de helpers privados se generaliza a todos los módulos de
`PRIVATE_HELPERS` (`auth` y, desde B1, `memberships`; B3 suma `payments` y B9a `members`), con
un control por fuente falsa; y `memberships` no importa `members.models`, `plans.models` ni
`settings.models` (lee por sus services).

S3-B9a (D7, S3-D73): `members/service.py` se parte en `rules.py` (puras y tipos), `detail.py` y
`changes.py` (vacíos hasta B9b y B10) y queda como fachada con `__all__`; ningún otro módulo
importa esos tres archivos.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.architecture._imports import PRIVATE_HELPERS, find_forbidden_imports

# Lo que `members/service.py` re-exporta como fachada (S3-B9a): las puras de `rules.py` y los
# contratos con sesión que siguen en el service. S3-B10 suma `reveal` (`detail.py`), `update`,
# `deactivate`, `reactivate` y los eventos `MemberUpdated` y `MemberDeactivated` (`changes.py`;
# Fase 4 del Sprint 3 suma `MemberReactivated`, S3-D89),
# y las puras `diff_fields`, `ensure_can_change` y `ADMIN_ONLY_FIELDS` (`rules.py`).
FACHADA_MEMBERS = frozenset(
    {
        "ADMIN_ONLY_FIELDS",
        "EMAIL_DATA_CLASS",
        "LIKE_ESCAPE",
        "MEMBER_CHIPS",
        "PHONE_DATA_CLASS",
        "MemberChipFilter",
        "MemberCreated",
        "MemberDeactivated",
        "MemberReactivated",
        "MemberUpdated",
        "QueryPlan",
        "active_ids",
        "chip_to_filter",
        "classify_query",
        "compute_warnings",
        "count",
        "create",
        "deactivate",
        "diff_fields",
        "ensure_can_change",
        "ensure_exists",
        "get",
        "get_ref",
        "id_by_document",
        "list",
        "mask",
        "names_for",
        "reactivate",
        "reveal",
        "search_ids",
        "update",
        "validate_member_input",
        # S4A-B6 (S4A-D21): el contacto para avisos y sus dos excepciones.
        "Contact",
        "InvalidPurpose",
        "MemberNotContactable",
        "contact_for_notification",
        "validate_purpose",
    }
)
PURAS_DE_RULES = frozenset(
    {
        "ADMIN_ONLY_FIELDS",
        "EMAIL_DATA_CLASS",
        "LIKE_ESCAPE",
        "MEMBER_CHIPS",
        "PHONE_DATA_CLASS",
        "MemberChipFilter",
        "QueryPlan",
        "chip_to_filter",
        "classify_query",
        "compute_warnings",
        "diff_fields",
        "ensure_can_change",
        "mask",
        "validate_member_input",
    }
)
# Lo que la fachada toma de `detail.py` y `changes.py` (S3-B10): el mismo objeto, no una copia.
DE_DETAIL = frozenset({"get", "reveal"})
DE_CHANGES = frozenset(
    {
        "update",
        "deactivate",
        "reactivate",
        "MemberUpdated",
        "MemberDeactivated",
        "MemberReactivated",
    }
)
# S4A-B6: lo que la fachada toma de `contact.py` y de `exceptions.py` (el mismo objeto).
DE_CONTACT = frozenset({"Contact", "contact_for_notification", "validate_purpose"})
DE_EXCEPTIONS = frozenset({"InvalidPurpose", "MemberNotContactable"})

MODULES_DIR = Path(__file__).resolve().parents[2] / "src" / "app" / "modules"


def test_sin_models_ni_routers_cruzados() -> None:
    violaciones = [
        str(v)
        for carpeta in sorted(p for p in MODULES_DIR.iterdir() if p.is_dir())
        for archivo in sorted(carpeta.rglob("*.py"))
        for v in find_forbidden_imports(archivo, module=carpeta.name)
    ]
    assert violaciones == [], "\n".join(violaciones)


def test_nadie_fuera_de_settings_importa_settings_models() -> None:
    """US-054 T10: los consumidores leen por `settings.service`; nunca por sus models."""
    violaciones = [
        str(v)
        for carpeta in sorted(p for p in MODULES_DIR.iterdir() if p.is_dir())
        if carpeta.name != "settings"
        for archivo in sorted(carpeta.rglob("*.py"))
        for v in find_forbidden_imports(archivo, module=carpeta.name)
        if v.imported.startswith("app.modules.settings.models")
    ]
    assert violaciones == [], "\n".join(violaciones)


def test_nadie_importa_los_helpers_privados_de_otro_modulo() -> None:
    """S2-D4 generalizada en S3-B1 (D7): los privados de cada módulo de `PRIVATE_HELPERS` solo los
    usa su propio módulo; los demás pasan por su `service.py`."""
    assert {"auth", "memberships"} <= set(PRIVATE_HELPERS)
    violaciones = [
        str(v)
        for carpeta in sorted(p for p in MODULES_DIR.iterdir() if p.is_dir())
        for archivo in sorted(carpeta.rglob("*.py"))
        for v in find_forbidden_imports(archivo, module=carpeta.name)
        if v.rule == "private_helper"
    ]
    assert violaciones == [], "\n".join(violaciones)


def test_los_privados_de_memberships_son_los_de_d7() -> None:
    assert (
        frozenset({"rules", "events", "sell", "lifecycle", "queries", "summary", "expirations"})
        == PRIVATE_HELPERS["memberships"]
    )
    for archivo in PRIVATE_HELPERS["memberships"]:
        assert (MODULES_DIR / "memberships" / f"{archivo}.py").is_file(), archivo


def test_los_privados_de_payments_son_los_de_d7() -> None:
    """S3-B3 (D7): `payments` nace partido tras la fachada `service.py`."""
    assert frozenset({"rules", "events", "queries"}) == PRIVATE_HELPERS["payments"]
    for archivo in PRIVATE_HELPERS["payments"]:
        assert (MODULES_DIR / "payments" / f"{archivo}.py").is_file(), archivo


def test_los_privados_de_audit_son_los_de_b4() -> None:
    """S4A-B3 y S4A-B4 (S4A-D18): `audit` nace partido; B3 dejó `verify` y B4 suma `queries` (lista
    y detalle) y `diff` (puras), los tres archivos existen y son privados del módulo."""
    assert frozenset({"verify", "queries", "diff"}) == PRIVATE_HELPERS.get("audit")
    for archivo in PRIVATE_HELPERS["audit"]:
        assert (MODULES_DIR / "audit" / f"{archivo}.py").is_file(), archivo


def test_los_privados_de_members_son_los_de_b9a() -> None:
    """S3-B9a (D7, S3-D73): `rules`, `detail` y `changes` existen y son privados de `members`;
    S4A-B6 (S4A-D21) suma `contact` (el contacto para avisos). Conjunto exacto."""
    assert frozenset({"rules", "detail", "changes", "contact"}) == PRIVATE_HELPERS.get("members")
    for archivo in PRIVATE_HELPERS["members"]:
        assert (MODULES_DIR / "members" / f"{archivo}.py").is_file(), archivo


def test_nadie_fuera_de_members_importa_rules_detail_ni_changes() -> None:
    privados = tuple(f"app.modules.members.{a}" for a in ("rules", "detail", "changes", "contact"))
    violaciones = [
        str(v)
        for carpeta in sorted(p for p in MODULES_DIR.iterdir() if p.is_dir())
        if carpeta.name != "members"
        for archivo in sorted(carpeta.rglob("*.py"))
        for v in find_forbidden_imports(archivo, module=carpeta.name)
        if v.imported.startswith(privados)
    ]
    assert violaciones == [], "\n".join(violaciones)
    falso = MODULES_DIR / "payments" / "queries.py"
    fuente = "from app.modules.members.rules import mask\nfrom app.modules.members import detail\n"
    assert sorted(
        (v.imported, v.rule)
        for v in find_forbidden_imports(falso, module="payments", source=fuente)
    ) == [
        ("app.modules.members.detail", "private_helper"),
        ("app.modules.members.rules", "private_helper"),
    ]


def test_members_service_es_fachada_con_all() -> None:
    """S3-B9a: `service.py` declara `__all__` y re-exporta las puras de `rules.py` (el mismo
    objeto, no una copia), así `tests/members` y los demás módulos siguen importando de él."""
    from app.modules.members import service

    exportados = getattr(service, "__all__", None)
    assert exportados is not None, "members/service.py sin __all__"
    assert len(exportados) == len(set(exportados)), "nombres repetidos en __all__"
    assert set(exportados) >= FACHADA_MEMBERS, sorted(FACHADA_MEMBERS - set(exportados))
    for nombre in exportados:
        assert hasattr(service, nombre), nombre
    rules = importlib.import_module("app.modules.members.rules")
    for nombre in PURAS_DE_RULES:
        assert getattr(service, nombre) is getattr(rules, nombre), nombre
    detail = importlib.import_module("app.modules.members.detail")
    for nombre in DE_DETAIL:
        assert getattr(service, nombre) is getattr(detail, nombre), nombre
    changes = importlib.import_module("app.modules.members.changes")
    for nombre in DE_CHANGES:
        assert getattr(service, nombre) is getattr(changes, nombre), nombre
    contact = importlib.import_module("app.modules.members.contact")
    for nombre in DE_CONTACT:
        assert getattr(service, nombre) is getattr(contact, nombre), nombre
    excepciones = importlib.import_module("app.modules.members.exceptions")
    for nombre in DE_EXCEPTIONS:
        assert getattr(service, nombre) is getattr(excepciones, nombre), nombre


@pytest.mark.parametrize("ajeno", ["members", "memberships", "auth", "settings"])
def test_payments_no_importa_models_ajenos(ajeno: str) -> None:
    """S3-B3: `payments` habla con los demás solo por su `service.py`, `schemas.py` y
    `exceptions.py` (regla de módulos 2), nunca por sus `models.py`."""
    violaciones = [
        str(v)
        for archivo in sorted((MODULES_DIR / "payments").rglob("*.py"))
        for v in find_forbidden_imports(archivo, module="payments")
        if v.imported.startswith(f"app.modules.{ajeno}.models")
    ]
    assert violaciones == [], "\n".join(violaciones)


@pytest.mark.parametrize("ajeno", ["members", "plans", "settings"])
def test_memberships_no_importa_models_de_socios_planes_ni_settings(ajeno: str) -> None:
    violaciones = [
        str(v)
        for archivo in sorted((MODULES_DIR / "memberships").rglob("*.py"))
        for v in find_forbidden_imports(archivo, module="memberships")
        if v.imported.startswith(f"app.modules.{ajeno}.models")
    ]
    assert violaciones == [], "\n".join(violaciones)


def test_control_un_privado_ajeno_y_un_models_ajeno_se_detectan() -> None:
    falso = MODULES_DIR / "payments" / "queries.py"
    fuente = (
        "from app.modules.memberships import sell\n"
        "from app.modules.memberships.rules import compute_status\n"
        "from app.modules.memberships import service as memberships_service\n"
        "def f():\n"
        "    from app.modules.members.models import Member\n"
    )
    reglas = sorted(
        (v.imported, v.rule)
        for v in find_forbidden_imports(falso, module="payments", source=fuente)
    )
    assert reglas == [
        ("app.modules.members.models", "foreign_models"),
        ("app.modules.memberships.rules", "private_helper"),
        ("app.modules.memberships.sell", "private_helper"),
    ]
    propio = MODULES_DIR / "memberships" / "service.py"
    assert (
        find_forbidden_imports(
            propio,
            module="memberships",
            source=fuente.replace(
                "    from app.modules.members.models import Member\n", "    pass\n"
            ),
        )
        == []
    )
