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


# S4B-B3b: `rotated_at` sale del reloj (S4B-D39) -------------------------------------------------

SERVICE_DE_ROTACION = SRC / "core" / "crypto" / "service.py"


def _asignaciones_de_rotated_at(fuente: str) -> list[ast.expr]:
    """Valores asignados a `rotated_at` (`x.rotated_at = v` o `rotated_at=v` en una llamada)."""
    arbol = ast.parse(fuente)
    valores: list[ast.expr] = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign):
            if any(isinstance(t, ast.Attribute) and t.attr == "rotated_at" for t in n.targets):
                valores.append(n.value)
        elif isinstance(n, ast.Call):
            valores.extend(k.value for k in n.keywords if k.arg == "rotated_at")
    return valores


def _viene_del_reloj(valor: ast.expr) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "current_clock"
        for n in ast.walk(valor)
    )


def test_rotated_at_de_service_sale_de_current_clock() -> None:
    fuente = SERVICE_DE_ROTACION.read_text(encoding="utf-8")
    valores = _asignaciones_de_rotated_at(fuente)
    assert valores, "start_rotation debe fijar rotated_at"
    assert all(_viene_del_reloj(v) for v in valores)
    assert _usos(SERVICE_DE_ROTACION) == []


def test_control_rotated_at_con_now_o_sin_reloj_se_detecta() -> None:
    mala = "def f(k):\n    k.rotated_at = datetime.now(UTC)\n"
    buena = "def f(k):\n    k.rotated_at = current_clock().now_utc()\n"
    kw = "def f():\n    update(T).values(rotated_at=func.now())\n"
    assert [_viene_del_reloj(v) for v in _asignaciones_de_rotated_at(mala)] == [False]
    assert [_viene_del_reloj(v) for v in _asignaciones_de_rotated_at(buena)] == [True]
    assert [_viene_del_reloj(v) for v in _asignaciones_de_rotated_at(kw)] == [False]
