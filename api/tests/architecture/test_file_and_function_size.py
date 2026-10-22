"""Tamaño de archivos y funciones de `api/src` (revisión Python H1 y M7; reglas de estilo del
equipo: archivos de 800 líneas como máximo y funciones de 50).

Antes `auth/service.py` tenía 1257 líneas y `main.create_app`, `change_password` y
`update_user` pasaban de 50. La prueba cuenta líneas físicas (docstrings incluidos) y, para las
funciones, de la línea del `def` a la última del cuerpo.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
MAX_LINEAS_ARCHIVO = 800
MAX_LINEAS_FUNCION = 50


def _archivos() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_hay_archivos_que_medir() -> None:
    assert len(_archivos()) > 50


def test_ningun_archivo_supera_800_lineas() -> None:
    largos = [
        f"{p.relative_to(SRC).as_posix()}: {n}"
        for p in _archivos()
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > MAX_LINEAS_ARCHIVO
    ]
    assert largos == [], "\n".join(largos)


def test_ninguna_funcion_supera_50_lineas() -> None:
    largas: list[str] = []
    for p in _archivos():
        arbol = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                lineas = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
                if lineas > MAX_LINEAS_FUNCION:
                    largas.append(f"{p.relative_to(SRC).as_posix()}:{nodo.lineno} {nodo.name}")
    assert largas == [], "\n".join(largas)
