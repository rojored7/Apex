"""La KEK solo se abre en `core/crypto` (S4B-B3a; S4B-D58, S4B-D76, H-3).

Por AST sobre `src/app`: una "apertura" es una llamada a `open`, `os.open` o a un método
`open`, `read_bytes` o `read_text` cuya expresión (receptor o argumentos) nombra la ruta de la KEK
(`CRYPTO_LOCAL_KEK_PATH`, `kek_path` o `.kek`). Solo `core/crypto/local_provider.py` (el
proveedor, que la carga) y `core/crypto/archive.py` (el respaldo con `age`) pueden abrirla: no hay
`read_kek` público ni lector alguno en el CLI.

Desviación del plan, declarada: la ruta se *nombra* (sin abrirla) en `core/config.py` (el ajuste),
`core/crypto/provider.py` (se la pasa al proveedor), `cli_ops/keys.py` (`init-keys` la crea),
`cli_ops/openapi.py` (valor ficticio) y `cli_ops/kek.py` (se la pasa a `archive`); ese listado es
`NOMBRAN_LA_RUTA` y cualquier otro archivo que la nombre falla.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
ABREN: Final = frozenset({"core/crypto/local_provider.py", "core/crypto/archive.py"})
NOMBRAN_LA_RUTA: Final = frozenset(
    {
        "core/config.py",
        "core/crypto/local_provider.py",
        "core/crypto/archive.py",
        "core/crypto/provider.py",
        "cli_ops/keys.py",
        "cli_ops/openapi.py",
        "cli_ops/kek.py",
    }
)
NOMBRES_DE_LA_KEK: Final = frozenset({"CRYPTO_LOCAL_KEK_PATH", "kek_path"})
METODOS_DE_APERTURA: Final = frozenset({"open", "read_bytes", "read_text"})


def _es_nombre_de_kek(nombre: str, amplio: bool = True) -> bool:
    """Amplio (aperturas): cualquier nombre con `kek`. Estrecho (`nombra_la_ruta`): solo los
    nombres exactos de la ruta y el atributo `kek` de `KeyPaths`."""
    if amplio:
        return nombre in NOMBRES_DE_LA_KEK or "kek" in nombre.lower()
    return nombre in NOMBRES_DE_LA_KEK or nombre == "kek"


def _nombra_la_kek(nodo: ast.AST, alias: frozenset[str] = frozenset(), amplio: bool = True) -> bool:
    """El nodo nombra la ruta de la KEK: un nombre o atributo con `kek` (sin importar mayúsculas,
    p. ej. `kek_file` o `ruta_kek`), `CRYPTO_LOCAL_KEK_PATH`, o un alias local de esos."""
    for sub in ast.walk(nodo):
        if isinstance(sub, ast.Name) and (
            (amplio and _es_nombre_de_kek(sub.id)) or sub.id in NOMBRES_DE_LA_KEK or sub.id in alias
        ):
            return True
        if isinstance(sub, ast.Attribute) and _es_nombre_de_kek(sub.attr, amplio):
            return True
    return False


def _alias_de_la_kek(arbol: ast.AST) -> frozenset[str]:
    """Nombres a los que se asigna algo que nombra la KEK (`p = settings.CRYPTO_LOCAL_KEK_PATH`),
    hasta un punto fijo de dos pasadas. Es por módulo, no por función: basta como candado."""
    alias: set[str] = set()
    for _ in range(2):
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Assign) and _nombra_la_kek(nodo.value, frozenset(alias)):
                alias.update(t.id for t in nodo.targets if isinstance(t, ast.Name))
    return frozenset(alias)


def aperturas_de_la_kek(fuente: str) -> list[int]:
    """Líneas de `fuente` donde se abre (o lee) una expresión que nombra la ruta de la KEK o un
    alias de ella."""
    arbol = ast.parse(fuente)
    alias = _alias_de_la_kek(arbol)
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        es_apertura = (isinstance(funcion, ast.Name) and funcion.id == "open") or (
            isinstance(funcion, ast.Attribute) and funcion.attr in METODOS_DE_APERTURA
        )
        if es_apertura and _nombra_la_kek(nodo, alias):
            lineas.append(nodo.lineno)
    return sorted(lineas)


def nombra_la_ruta(fuente: str) -> bool:
    return _nombra_la_kek(ast.parse(fuente), amplio=False)


def _archivos() -> list[tuple[str, str]]:
    return [
        (p.relative_to(SRC).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted(SRC.rglob("*.py"))
    ]


# Reglas sobre el árbol real -------------------------------------------------------------------


def test_solo_local_provider_y_archive_abren_la_kek() -> None:
    abren = {r for r, f in _archivos() if aperturas_de_la_kek(f)}
    assert abren <= ABREN, sorted(abren - ABREN)


def test_local_provider_y_archive_abren_la_kek() -> None:
    """Sin esto la regla anterior no vigilaría nada: `archive.py` (Verde) abre la KEK de
    `export_kek_file` y el proveedor la carga con `read_bytes`."""
    abren = {r for r, f in _archivos() if aperturas_de_la_kek(f)}
    assert abren == ABREN, sorted(ABREN ^ abren)


def test_ningun_otro_archivo_nombra_la_ruta_de_la_kek() -> None:
    nombran = {r for r, f in _archivos() if nombra_la_ruta(f)}
    assert nombran <= NOMBRAN_LA_RUTA, sorted(nombran - NOMBRAN_LA_RUTA)


def test_no_existe_un_lector_publico_de_la_kek() -> None:
    for relativo, fuente in _archivos():
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert nodo.name not in {"read_kek", "get_kek", "load_kek"}, (relativo, nodo.name)


def test_cli_ops_kek_no_abre_la_kek() -> None:
    fuente = (SRC / "cli_ops" / "kek.py").read_text(encoding="utf-8")
    assert aperturas_de_la_kek(fuente) == []


# Controles con fuentes falsas ------------------------------------------------------------------


def test_control_las_formas_de_apertura_se_detectan() -> None:
    assert aperturas_de_la_kek("open(settings.CRYPTO_LOCAL_KEK_PATH, 'rb')\n") == [1]
    assert aperturas_de_la_kek("settings.CRYPTO_LOCAL_KEK_PATH.read_bytes()\n") == [1]
    assert aperturas_de_la_kek("Path(kek_path).open('rb')\n") == [1]
    assert aperturas_de_la_kek("def f(paths):\n    return paths.kek.read_text()\n") == [2]
    assert aperturas_de_la_kek("open('otro.txt')\n") == []
    assert aperturas_de_la_kek("p = settings.CRYPTO_LOCAL_KEK_PATH\n") == []


def test_control_una_fuente_falsa_en_cli_ops_que_abre_la_kek_se_detecta() -> None:
    falsa = "def leer(settings):\n    return open(settings.CRYPTO_LOCAL_KEK_PATH, 'rb').read()\n"
    assert aperturas_de_la_kek(falsa) == [2]
    assert "cli_ops/falso.py" not in ABREN
    assert "cli_ops/falso.py" not in NOMBRAN_LA_RUTA
    assert nombra_la_ruta(falsa)


def test_control_los_alias_y_los_nombres_con_kek_se_detectan() -> None:
    """S4B-D134 (L6): no basta con la cadena exacta; un alias o `ruta_kek` también cuentan."""
    assert aperturas_de_la_kek("p = settings.CRYPTO_LOCAL_KEK_PATH\nopen(p, 'rb')\n") == [2]
    assert aperturas_de_la_kek(
        "q = p = settings.CRYPTO_LOCAL_KEK_PATH\nPath(q).read_bytes()\n"
    ) == [2]
    assert aperturas_de_la_kek("Path(ruta_kek).read_bytes()\n") == [1]
    assert aperturas_de_la_kek("os.open(Kek_File, 0)\n") == [1]
    assert aperturas_de_la_kek("p = settings.OTRA\nopen(p)\n") == []
