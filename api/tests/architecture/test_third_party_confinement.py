"""Terceros confinados a un solo sitio (S4B-B1; S4B-D21).

Por AST sobre `src/app` (también imports dentro de funciones, relativos ignorados porque ningún
tercero es relativo, y `importlib.import_module("x")` / `__import__("x")` con cadena literal):

- `openpyxl` y `defusedxml` solo se importan bajo `imports/` (la lectura de la plantilla);
- `subprocess` solo en `core/crypto/archive.py` (el binario `age`) y, desde B3a, ese archivo SÍ
  lo importa (S4B-D21): lista de un solo archivo con un importador real;
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


def test_subprocess_tiene_exactamente_un_importador_real_archive() -> None:
    """S4B-B3a: la regla deja de ser preventiva; `archive.py` importa `subprocess`."""
    assert importadores("subprocess") == SUBPROCESS_PERMITIDO


def test_archive_lanza_age_con_lista_sin_shell_y_con_entorno_vacio() -> None:
    """S4B-D58: `Popen([...], env={}, shell=False)`; nunca `shell=True`, `os.system` ni `run`
    con una cadena; la KEK entra por descriptor, no por el entorno."""
    fuente = (SRC / "core" / "crypto" / "archive.py").read_text(encoding="utf-8")
    llamadas_popen = [
        n
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "Popen"
    ]
    assert llamadas_popen, "archive.py no lanza age con Popen"
    for llamada in llamadas_popen:
        claves = {k.arg: k.value for k in llamada.keywords}
        assert isinstance(claves.get("env"), ast.Dict) and not claves["env"].keys, "env={}"
        shell = claves.get("shell")
        assert shell is None or (isinstance(shell, ast.Constant) and shell.value is False)
    assert "shell=True" not in fuente and "os.system" not in fuente
    assert "--passphrase" not in fuente


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


@pytest.mark.parametrize("relativo", ["worker/jobs/backup_check.py", "core/backup_status.py"])
def test_el_job_y_el_estado_de_backup_no_lanzan_procesos(relativo: str) -> None:
    """S4B-B2 (S4B-D59): el worker no ejecuta `age`; ni `subprocess` ni `asyncio.subprocess`."""
    fuente = (SRC / relativo).read_text(encoding="utf-8")
    assert "subprocess" not in terceros_importados(fuente)
    assert "create_subprocess" not in fuente
    assert "os.system" not in fuente
    assert "popen" not in fuente.lower()


# S4B-B3b: ningún archivo nuevo importa `pyrage` ni lanza procesos (S4B-D37, D58) ----------------

ARCHIVOS_DE_B3B: Final = (
    "core/crypto/discovery.py",
    "core/crypto/service.py",
    "cli_ops/rotate_key.py",
    "cli_ops/retire_key.py",
)


def test_los_archivos_de_b3b_no_importan_pyrage_subprocess_ni_openpyxl() -> None:
    for relativo in ARCHIVOS_DE_B3B:
        ruta = SRC / relativo
        assert ruta.is_file(), relativo
        importados = terceros_importados(ruta.read_text(encoding="utf-8"))
        assert not importados & {"pyrage", "subprocess", "openpyxl", "defusedxml"}, relativo


def test_pyrage_sigue_ausente_con_los_archivos_de_b3b_presentes() -> None:
    """Control de la regla global: los cuatro archivos nuevos están en el barrido y `pyrage` no
    aparece en ninguno."""
    barridos = {r for r, _ in _archivos()}
    assert set(ARCHIVOS_DE_B3B) <= barridos
    assert importadores("pyrage") == set()


def test_control_pyrage_en_un_archivo_de_b3b_se_detectaria() -> None:
    assert terceros_importados("import pyrage\n") == {"pyrage"}
    assert terceros_importados("def f():\n    import subprocess\n") == {"subprocess"}


# S5-B1: `httpx` confinado al proveedor de OpenBao (S5-D17, S5-D29) -------------------------------

HTTPX_PERMITIDO: Final = frozenset({"core/crypto/openbao_provider.py"})  # B4 suma alerts_telegram


def httpx_fuera_de_sitio(relativo: str, fuente: str) -> bool:
    return relativo not in HTTPX_PERMITIDO and "httpx" in terceros_importados(fuente)


def test_httpx_solo_en_el_proveedor_de_openbao() -> None:
    fuera = sorted(importadores("httpx") - HTTPX_PERMITIDO)
    assert fuera == [], fuera


def test_httpx_tiene_exactamente_un_importador_real_el_proveedor() -> None:
    assert importadores("httpx") == HTTPX_PERMITIDO


@pytest.mark.parametrize(
    "relativo", ["core/health.py", "core/alerts.py", "main.py", "modules/members/service.py"]
)
def test_control_httpx_fuera_del_proveedor_falla(relativo: str) -> None:
    assert httpx_fuera_de_sitio(relativo, "import httpx\n")
    assert httpx_fuera_de_sitio(relativo, "from httpx import AsyncClient\n")
    assert httpx_fuera_de_sitio(relativo, "import importlib\nimportlib.import_module('httpx')\n")
    assert not httpx_fuera_de_sitio("core/crypto/openbao_provider.py", "import httpx\n")
