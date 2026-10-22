"""Ningún módulo importa `models` ni `router` ajenos (US-022 T4; reglas de módulos 1 y 2)."""

from __future__ import annotations

from pathlib import Path

from tests.architecture._imports import find_forbidden_imports

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
