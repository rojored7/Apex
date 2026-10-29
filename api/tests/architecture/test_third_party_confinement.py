"""Terceros confinados a un solo sitio (S4B-B1; S4B-D21).

Por AST sobre `src/app` (también imports dentro de funciones, relativos ignorados porque ningún
tercero es relativo, y `importlib.import_module("x")` / `__import__("x")` con cadena literal):

- `openpyxl` y `defusedxml` solo se importan bajo `imports/` (la lectura de la plantilla);
- `subprocess` solo en `core/crypto/archive.py` (el binario `age`, B2/B3a); vigente desde ya:
  hoy ningún archivo lo importa;
- `pyrage` no se importa en ninguna parte (S4B-D37: se descartó por licencia);
- `imports/members_xlsx.py` sí usa `openpyxl` (es quien lee el libro).
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
SOLO_BAJO_IMPORTS: Final = ("openpyxl", "defusedxml")
SUBPROCESS_PERMITIDO: Final = frozenset({"core/crypto/archive.py"})
NUNCA: Final = ("pyrage",)


def terceros_importados(fuente: str) -> set[str]:
    """Raíces (`openpyxl` de `openpyxl.xml.x`) de todo import absoluto de `fuente`."""
    salida: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            salida.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            salida.add(nodo.module.split(".")[0])
        elif (
            isinstance(nodo, ast.Call)
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
            and isinstance(nodo.args[0].value, str)
            and (
                (isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "import_module")
                or (isinstance(nodo.func, ast.Name) and nodo.func.id == "__import__")
            )
        ):
            salida.add(nodo.args[0].value.split(".")[0])
    return salida


def _archivos() -> list[tuple[str, str]]:
    return [
        (p.relative_to(SRC).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted(SRC.rglob("*.py"))
    ]


def importadores(tercero: str) -> set[str]:
    return {r for r, f in _archivos() if tercero in terceros_importados(f)}


def fuera_de_imports(relativo: str, fuente: str) -> list[str]:
    """`openpyxl` / `defusedxml` importados desde un archivo que no está bajo `imports/`."""
    if relativo.startswith("imports/"):
        return []
    return sorted(set(SOLO_BAJO_IMPORTS) & terceros_importados(fuente))


def subprocess_fuera_de_archive(relativo: str, fuente: str) -> bool:
    return relativo not in SUBPROCESS_PERMITIDO and "subprocess" in terceros_importados(fuente)


# Reglas sobre el árbol real -------------------------------------------------------------------


@pytest.mark.parametrize("tercero", SOLO_BAJO_IMPORTS)
def test_openpyxl_y_defusedxml_solo_bajo_imports(tercero: str) -> None:
    fuera = sorted(r for r in importadores(tercero) if not r.startswith("imports/"))
    assert fuera == [], fuera


def test_imports_members_xlsx_es_quien_lee_el_libro_con_openpyxl() -> None:
    assert "imports/members_xlsx.py" in importadores("openpyxl")


def test_subprocess_solo_en_core_crypto_archive() -> None:
    fuera = sorted(importadores("subprocess") - SUBPROCESS_PERMITIDO)
    assert fuera == [], fuera


@pytest.mark.parametrize("tercero", NUNCA)
def test_pyrage_no_se_importa_en_ninguna_parte(tercero: str) -> None:
    assert importadores(tercero) == set()


# Controles con fuentes falsas ------------------------------------------------------------------

FALSAS: Final = {
    "import openpyxl\n": {"openpyxl"},
    "from openpyxl import load_workbook\n": {"openpyxl"},
    "from openpyxl.xml import DEFUSEDXML\n": {"openpyxl"},
    "import defusedxml.ElementTree as ET\n": {"defusedxml"},
    "def f():\n    import subprocess\n": {"subprocess"},
    "import importlib\nimportlib.import_module('subprocess')\n": {"importlib", "subprocess"},
    "x = __import__('pyrage')\n": {"pyrage"},
    "from . import openpyxl\n": set(),
}


@pytest.mark.parametrize(("fuente", "esperado"), sorted(FALSAS.items()))
def test_control_el_analizador_ve_cada_forma_de_import(fuente: str, esperado: set[str]) -> None:
    assert terceros_importados(fuente) == esperado


@pytest.mark.parametrize(
    "relativo",
    ["modules/members/service.py", "cli_ops/import_members.py", "seed/apply.py", "main.py"],
)
def test_control_openpyxl_o_defusedxml_fuera_de_imports_falla(relativo: str) -> None:
    assert fuera_de_imports(relativo, "import openpyxl\n") == ["openpyxl"]
    assert fuera_de_imports(relativo, "from defusedxml import ElementTree\n") == ["defusedxml"]


def test_control_bajo_imports_si_pueden_usarlos() -> None:
    assert fuera_de_imports("imports/members_xlsx.py", "import openpyxl\n") == []
    assert fuera_de_imports("imports/report.py", "import defusedxml\n") == []


@pytest.mark.parametrize("relativo", ["cli.py", "worker/jobs/backup_check.py", "core/jobs.py"])
def test_control_subprocess_fuera_de_archive_falla(relativo: str) -> None:
    assert subprocess_fuera_de_archive(relativo, "import subprocess\n")
    assert not subprocess_fuera_de_archive("core/crypto/archive.py", "import subprocess\n")
