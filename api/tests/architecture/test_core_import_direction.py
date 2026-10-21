"""Dirección de imports de `core` (US-014, US-015; absorbe el grafo de US-029 y US-034).

- `core` nunca importa `app.modules`.
- `core/crypto` nunca importa `core/audit`.
- `core/audit` solo toma `core/crypto/digest` de `core/crypto`.
- `core/context.py` solo importa la biblioteca estándar.
- `core/db.py` no importa `core/audit` ni `core/crypto`.
- Sin ciclos entre módulos de `core` a nivel de módulo (los imports perezosos dentro de
  funciones no cuentan).
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


def _imports_de_modulo(path: Path) -> list[str]:
    """Solo los imports del nivel superior (no los perezosos dentro de funciones)."""
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nombres: list[str] = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Import):
            nombres.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
    return nombres


def _modulo(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("").as_posix().replace("/", ".")
    return "app." + rel.removesuffix(".__init__")


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


def test_context_solo_biblioteca_estandar() -> None:
    assert [n for n in _imports(CORE / "context.py") if n.startswith("app")] == []


def test_db_no_importa_audit_ni_crypto() -> None:
    nombres = _imports(CORE / "db.py")
    assert [n for n in nombres if n.startswith(("app.core.audit", "app.core.crypto"))] == []


def test_sin_ciclos_entre_modulos_de_core() -> None:
    archivos = sorted(CORE.rglob("*.py"))
    grafo: dict[str, set[str]] = {}
    for path in archivos:
        origen = _modulo(path)
        grafo[origen] = {
            n for n in _imports_de_modulo(path) if n.startswith("app.core") and n != origen
        }

    estado: dict[str, int] = {}
    pila: list[str] = []
    ciclos: list[str] = []

    def visitar(nodo: str) -> None:
        estado[nodo] = 1
        pila.append(nodo)
        for destino in sorted(grafo.get(nodo, ())):
            if estado.get(destino) == 1:
                ciclos.append(" -> ".join([*pila[pila.index(destino) :], destino]))
            elif destino not in estado and destino in grafo:
                visitar(destino)
        pila.pop()
        estado[nodo] = 2

    for origen in grafo:
        if origen not in estado:
            visitar(origen)
    assert ciclos == []
