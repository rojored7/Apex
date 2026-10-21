"""Nadie lee el entorno fuera de `core/config.py` (US-011, T7).

Todo entra por `Settings`; así `.env.example` y las pruebas de configuración
cubren de verdad todas las variables.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
PERMITIDO = "core/config.py"
ATRIBUTOS = {"environ", "getenv", "putenv", "unsetenv"}


def _usos(path: Path) -> list[int]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    alias_os = {"os"}
    nombres_directos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name == "os":
                    alias_os.add(a.asname or "os")
        elif isinstance(nodo, ast.ImportFrom) and nodo.module == "os":
            for a in nodo.names:
                if a.name in ATRIBUTOS:
                    nombres_directos.add(a.asname or a.name)
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if (
            isinstance(nodo, ast.Attribute)
            and nodo.attr in ATRIBUTOS
            and isinstance(nodo.value, ast.Name)
            and nodo.value.id in alias_os
        ) or (isinstance(nodo, ast.Name) and nodo.id in nombres_directos):
            lineas.append(nodo.lineno)
    return lineas


def test_nadie_lee_os_environ_fuera_de_config() -> None:
    violaciones = [
        f"{path.relative_to(SRC).as_posix()}:{linea}"
        for path in sorted(SRC.rglob("*.py"))
        if path.relative_to(SRC).as_posix() != PERMITIDO
        for linea in _usos(path)
    ]
    assert violaciones == []


def test_el_analizador_detecta_los_tres_usos(tmp_path: Path) -> None:
    archivo = tmp_path / "x.py"
    archivo.write_text(
        "import os\nfrom os import getenv as g\nos.environ['A']\nos.getenv('B')\ng('C')\n",
        encoding="utf-8",
    )
    assert _usos(archivo) == [3, 4, 5]
