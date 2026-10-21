"""Nunca `create_all` ni `drop_all` en el código del api (US-012, T12; CLAUDE.md datos 7).

Las tablas nacen solo por migraciones de Alembic. `create_all` queda permitido
únicamente dentro de `tests/`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
PROHIBIDOS = {"create_all", "drop_all"}


def _usos(path: Path) -> list[int]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        nodo.lineno
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr in PROHIBIDOS
    ]


def test_sin_create_all_en_src() -> None:
    violaciones = [
        f"{path.relative_to(SRC).as_posix()}:{linea}"
        for path in sorted(SRC.rglob("*.py"))
        for linea in _usos(path)
    ]
    assert violaciones == []


def test_el_analizador_detecta_create_all(tmp_path: Path) -> None:
    archivo = tmp_path / "x.py"
    archivo.write_text("Base.metadata.create_all(engine)\nmeta.drop_all(e)\n", encoding="utf-8")
    assert _usos(archivo) == [1, 2]
