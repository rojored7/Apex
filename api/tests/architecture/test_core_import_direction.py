"""Dirección de imports de `core` (US-014 primera versión; US-015 la completa).

- `core` nunca importa `app.modules`.
- `core/crypto` nunca importa `core/audit` (cuando existan).
- `core/audit` solo toma `core/crypto/digest` de `core/crypto` (cuando exista).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
CORE = SRC / "core"


def _imports(path: Path) -> list[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nombres: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
    return nombres


def test_core_no_importa_modulos() -> None:
    violaciones = [
        f"{path.relative_to(SRC).as_posix()}: {nombre}"
        for path in sorted(CORE.rglob("*.py"))
        for nombre in _imports(path)
        if nombre.startswith("app.modules")
    ]
    assert violaciones == []


def test_crypto_no_importa_audit_y_audit_solo_toma_digest() -> None:
    violaciones: list[str] = []
    for path in sorted((CORE / "crypto").rglob("*.py")) if (CORE / "crypto").is_dir() else []:
        violaciones += [
            f"{path.name}: {n}" for n in _imports(path) if n.startswith("app.core.audit")
        ]
    audit = CORE / "audit.py"
    if audit.is_file():
        violaciones += [
            f"audit.py: {n}"
            for n in _imports(audit)
            if n.startswith("app.core.crypto") and n != "app.core.crypto.digest"
        ]
    assert violaciones == []
