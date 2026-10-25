"""Ningún módulo importa `models` ni `router` ajenos (US-022 T4; reglas de módulos 1 y 2).

S3-B1 (D7, US-084): la prueba de helpers privados se generaliza a todos los módulos de
`PRIVATE_HELPERS` (`auth` y, desde B1, `memberships`; B3 suma `payments` y B9 `members`), con un
control por fuente falsa; y `memberships` no importa `members.models`, `plans.models` ni
`settings.models` (lee por sus services).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture._imports import PRIVATE_HELPERS, find_forbidden_imports

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
        frozenset({"rules", "events", "sell", "lifecycle", "queries"})
        == PRIVATE_HELPERS["memberships"]
    )
    for archivo in PRIVATE_HELPERS["memberships"]:
        assert (MODULES_DIR / "memberships" / f"{archivo}.py").is_file(), archivo


def test_los_privados_de_payments_son_los_de_d7() -> None:
    """S3-B3 (D7): `payments` nace partido tras la fachada `service.py`."""
    assert frozenset({"rules", "events", "queries"}) == PRIVATE_HELPERS["payments"]
    for archivo in PRIVATE_HELPERS["payments"]:
        assert (MODULES_DIR / "payments" / f"{archivo}.py").is_file(), archivo


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
