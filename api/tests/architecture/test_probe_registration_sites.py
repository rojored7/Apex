"""Solo el dueño registra un puerto de `wods` (S9-B2, revisión de seguridad LOW-2).

`set_records_probe` solo se llama desde `athletes/service.py` y `set_results_probe` solo desde
`results/service.py` (y desde `tests/`, que registra dobles): un módulo que registrara un puerto
permisivo desactivaría el bloqueo de unidad, tipo de marca y resultados. Barrido por AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app

SRC = Path(app.__file__).resolve().parent
DUENOS: dict[str, str] = {
    "set_records_probe": "modules/athletes/service.py",
    "set_results_probe": "modules/results/service.py",
}
# Donde se DEFINEN y se reexportan (no son llamadas): `wods` mismo.
DEFINIDA_EN = {"modules/wods/probe.py", "modules/wods/service.py"}


def llamadas_indebidas(fuente: str, ruta: str) -> list[str]:
    """Llamadas a los registradores fuera de su dueño en `fuente` (ruta relativa a `app/`)."""
    indebidas: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        func = nodo.func
        nombre = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if nombre in DUENOS and ruta != DUENOS[nombre] and ruta not in DEFINIDA_EN:
            indebidas.append(f"{ruta}:{nodo.lineno} {nombre}")
    return indebidas


def test_el_detector_ve_una_llamada_indebida_sintetica() -> None:
    codigo = "from app.modules.wods import service as w\nw.set_records_probe(Permisivo())\n"
    assert llamadas_indebidas(codigo, "modules/members/service.py") == [
        "modules/members/service.py:2 set_records_probe"
    ]
    assert llamadas_indebidas(codigo, "modules/athletes/service.py") == []
    assert llamadas_indebidas("set_results_probe(x)", "modules/athletes/service.py") != []


def test_solo_el_dueno_registra_cada_puerto_en_src() -> None:
    indebidas: list[str] = []
    for archivo in SRC.rglob("*.py"):
        ruta = archivo.relative_to(SRC).as_posix()
        indebidas += llamadas_indebidas(archivo.read_text(encoding="utf-8"), ruta)
    assert indebidas == []
