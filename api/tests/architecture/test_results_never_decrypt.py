"""`results` nunca descifra ni importa el bus de cifrado (S8-B1, S8-D18; revisión de seguridad).

La tabla de resultados y las proyecciones del tablero y de la TV no llevan columnas cifradas: los
nombres salen de `members.service` (`names_for`, `board_names`), que ya devuelve texto en claro
del nombre y el apellido. Por AST, ningún archivo de `modules/results` importa `app.core.crypto`
ni nombra `reveal`, `decrypt`, `Encrypted` ni `blind_index`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app

RESULTS = Path(app.__file__).resolve().parent / "modules" / "results"
TV = Path(app.__file__).resolve().parent / "modules" / "tv"  # S8-C2: la TV tampoco descifra
PROHIBIDOS = frozenset({"reveal", "decrypt", "Encrypted", "blind_index", "encrypt"})


def _importa_el_bus(nodo: ast.AST, nombre: str) -> list[str]:
    """Imports estáticos del bus: `from app.core.crypto...`, `from app.core import crypto` e
    `import app.core.crypto...`."""
    if isinstance(nodo, ast.ImportFrom):
        modulo = nodo.module or ""
        if modulo.startswith("app.core.crypto"):
            return [f"{nombre}:{nodo.lineno} importa {modulo}"]
        if modulo == "app.core" and any(a.name == "crypto" for a in nodo.names):
            return [f"{nombre}:{nodo.lineno} importa app.core.crypto"]
    if isinstance(nodo, ast.Import):
        return [
            f"{nombre}:{nodo.lineno} importa {a.name}"
            for a in nodo.names
            if a.name.startswith("app.core.crypto")
        ]
    return []


def _import_dinamico(nodo: ast.AST, nombre: str) -> list[str]:
    """`importlib.import_module(...)` y `__import__(...)`: la puerta dinámica."""
    if not isinstance(nodo, ast.Call):
        return []
    f = nodo.func
    llamada = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
    if llamada in {"import_module", "__import__"}:
        return [f"{nombre}:{nodo.lineno} importa de forma dinámica"]
    return []


def _hallazgos(fuente: str, nombre: str) -> list[str]:
    arbol = ast.parse(fuente)
    salida: list[str] = []
    for nodo in ast.walk(arbol):
        salida += _importa_el_bus(nodo, nombre) + _import_dinamico(nodo, nombre)
        if isinstance(nodo, ast.Name | ast.Attribute):
            usado = nodo.id if isinstance(nodo, ast.Name) else nodo.attr
            if usado in PROHIBIDOS:
                salida.append(f"{nombre}:{nodo.lineno} nombra {usado}")
    return salida


def test_results_no_importa_ni_nombra_el_bus_de_cifrado() -> None:
    archivos = sorted([*RESULTS.rglob("*.py"), *TV.rglob("*.py")])
    assert (RESULTS / "record.py").is_file() and (TV / "rules.py").is_file() and archivos
    encontrados = [h for p in archivos for h in _hallazgos(p.read_text(encoding="utf-8"), p.name)]
    assert encontrados == [], "\n".join(encontrados)


def test_el_control_detecta_un_reveal_y_un_import_del_bus() -> None:
    assert _hallazgos("from app.core.crypto.types import reveal\n", "x.py")
    assert _hallazgos("valor = reveal(x)\n", "x.py")
    assert not _hallazgos("valor = nombres_de(x)\n", "x.py")


def test_la_tabla_de_resultados_no_tiene_columnas_cifradas() -> None:
    from app.core.crypto.types import Encrypted
    from app.modules.results.models import WodResult

    cifradas = [c.name for c in WodResult.__table__.columns if isinstance(c.type, Encrypted)]
    assert cifradas == []
