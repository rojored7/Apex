"""Ningún archivo de `src/app` fuera del bus importa criptografía (CLAUDE.md, bus regla 8).

Primera versión (US-002): recorre el árbol real con `ast`, independiente de ruff.
US-023, US-031 y las siguientes la amplían.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
BANNED = ("cryptography", "oqs", "hashlib", "hmac", "jwt", "argon2")


def _permitido(path: Path) -> bool:
    rel = path.relative_to(SRC).as_posix()
    return (
        rel.startswith("core/crypto/")
        or rel == "core/security.py"
        or rel.startswith("core/security/")
    )


def _imports(path: Path) -> Iterator[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                yield alias.name
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            yield nodo.module


def _es_prohibido(nombre: str) -> bool:
    return any(nombre == b or nombre.startswith(b + ".") for b in BANNED)


def test_sin_imports_de_criptografia_fuera_del_bus() -> None:
    violaciones = [
        f"{path.relative_to(SRC).as_posix()}: {nombre}"
        for path in sorted(SRC.rglob("*.py"))
        if not _permitido(path)
        for nombre in _imports(path)
        if _es_prohibido(nombre)
    ]
    assert violaciones == []


def test_el_analizador_detecta_un_import_prohibido(tmp_path: Path) -> None:
    archivo = tmp_path / "service.py"
    archivo.write_text("import hashlib\nfrom cryptography.hazmat import x\n", encoding="utf-8")
    assert [n for n in _imports(archivo) if _es_prohibido(n)] == ["hashlib", "cryptography.hazmat"]


def test_el_analizador_respeta_core_crypto() -> None:
    assert _permitido(SRC / "core" / "crypto" / "bus.py")
    assert _permitido(SRC / "core" / "security.py")
    assert not _permitido(SRC / "core" / "audit.py")
    assert not _permitido(SRC / "modules" / "members" / "service.py")
