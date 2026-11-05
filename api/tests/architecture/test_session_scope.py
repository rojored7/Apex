"""N-1 (revisión de seguridad V10): toda ruta que abre la sesión lo hace con `SessionDep`.

`Depends(get_session)` sin `scope="function"` confirma DESPUÉS de enviar la respuesta en
FastAPI 0.157 (el cliente recibe 200/201 de una escritura que puede revertirse). Además, si una
ruta mezcla las dos formas FastAPI crea dos sesiones (la clave de caché incluye el alcance). La
prueba recorre el árbol de dependencias efectivo de `create_app()`: cada nodo cuya llamada es
`get_session` debe tener `scope == "function"`, y cada ruta usa a lo sumo una sesión.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from fastapi.dependencies.models import Dependant

from app.core.config import Settings
from app.core.db import get_session
from app.core.security import effective_routes
from app.main import create_app


def _nodos(dependant: Dependant) -> Iterator[Dependant]:
    yield dependant
    for hijo in dependant.dependencies:
        yield from _nodos(hijo)


def test_toda_sesion_de_ruta_tiene_alcance_de_funcion(settings_prueba: Settings) -> None:
    rutas, _ = effective_routes(create_app(settings_prueba, run_migrations_on_startup=False))
    revisadas = 0
    malas: list[str] = []
    for ruta in rutas:
        sesiones = [n for n in _nodos(ruta.dependant) if n.call is get_session]
        if not sesiones:
            continue
        revisadas += 1
        alcances = {n.scope for n in sesiones}
        if alcances != {"function"}:
            malas.append(f"{sorted(ruta.methods)} {ruta.path}: {alcances}")
    assert revisadas >= 20, revisadas  # auth, users, settings, members, plans
    assert malas == [], "\n".join(malas)


# S5-B12 (S5-D41, S5-D60, E9): el generador del CSV abre su propia sesión -----------------------

MODULES = Path(__file__).resolve().parents[2] / "src" / "app" / "modules"


def _generadores(archivo: Path) -> list[ast.AsyncFunctionDef]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    return [
        f
        for f in ast.walk(arbol)
        if isinstance(f, ast.AsyncFunctionDef)
        and any(isinstance(n, ast.Yield) for n in ast.walk(f))
    ]


def test_los_generadores_de_exports_no_reciben_la_sesion_de_la_peticion_y_abren_la_propia() -> None:
    """En `members/exports.py` y `payments/exports.py` hay al menos un generador asíncrono; ninguno
    recibe un parámetro `session` (la de la petición ya cerró cuando empieza el cuerpo) y el
    archivo abre sesiones con `get_sessionmaker()` (Rojo B12)."""
    for modulo in ("members", "payments"):
        archivo = MODULES / modulo / "exports.py"
        generadores = _generadores(archivo)
        assert generadores, f"{modulo}/exports.py sin generador asíncrono"
        for gen in generadores:
            nombres = {a.arg for a in gen.args.args + gen.args.kwonlyargs}
            assert "session" not in nombres, f"{modulo}.{gen.name} recibe la sesión de la petición"
        assert "get_sessionmaker" in archivo.read_text(encoding="utf-8"), modulo
