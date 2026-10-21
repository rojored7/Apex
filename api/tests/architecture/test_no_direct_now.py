"""El "ahora" y el "hoy" salen solo de `core/clock.py` (US-013, T5; Q28).

Prohíbe `datetime.now()`, `datetime.utcnow()`, `datetime.today()` y `date.today()`
en `src/app/**` fuera de `core/clock.py`, incluidos los alias.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
PERMITIDO = "core/clock.py"
METODOS = {"now", "utcnow", "today"}


def _usos(path: Path) -> list[int]:
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modulos = set()  # alias del módulo datetime: datetime.datetime.now()
    clases = set()  # alias de las clases datetime y date: dt.now()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name == "datetime":
                    modulos.add(a.asname or "datetime")
        elif isinstance(nodo, ast.ImportFrom) and nodo.module == "datetime":
            for a in nodo.names:
                if a.name in {"datetime", "date"}:
                    clases.add(a.asname or a.name)
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)):
            continue
        if nodo.func.attr not in METODOS:
            continue
        objetivo = nodo.func.value
        if isinstance(objetivo, ast.Name) and objetivo.id in clases:
            lineas.append(nodo.lineno)
        elif (
            isinstance(objetivo, ast.Attribute)
            and objetivo.attr in {"datetime", "date"}
            and isinstance(objetivo.value, ast.Name)
            and objetivo.value.id in modulos
        ):
            lineas.append(nodo.lineno)
    return lineas


def test_nadie_usa_now_ni_today_fuera_del_reloj() -> None:
    violaciones = [
        f"{path.relative_to(SRC).as_posix()}:{linea}"
        for path in sorted(SRC.rglob("*.py"))
        if path.relative_to(SRC).as_posix() != PERMITIDO
        for linea in _usos(path)
    ]
    assert violaciones == []


def test_el_analizador_detecta_alias(tmp_path: Path) -> None:
    archivo = tmp_path / "x.py"
    archivo.write_text(
        "import datetime as modulo\n"
        "from datetime import datetime as dt, date\n"
        "modulo.datetime.now()\n"
        "dt.utcnow()\n"
        "date.today()\n"
        "dt.now()\n"
        "otra_cosa.now()\n",
        encoding="utf-8",
    )
    assert _usos(archivo) == [3, 4, 5, 6]
