"""Fronteras del worker y de `cli.py` (US-113; S4A-D10, S4A-D73).

El worker es capa de aplicación como `cli.py`: de los módulos solo importa `service`, `schemas` y
`exceptions`. Se vigila por `ast` (con `find_forbidden_imports` de `_imports.py`, que
`test_no_cross_models.py` no aplica fuera de `app/modules/`):
- ningún archivo de `app/worker/**` ni `app/cli.py` importa `app.modules.<x>.models`,
  `app.modules.<x>.router` ni un helper privado de `PRIVATE_HELPERS`;
- ningún archivo de `app/worker/**` escribe SQL: sin llamadas `text(...)` ni
  `.exec_driver_sql(...)` (todo el SQL del worker vive en `core/jobs.py` o llega por services);
- los únicos importadores de `app.core.jobs` dentro de `src/app` son archivos de `app/worker/`
  (ni `main.py`, ni `core/health.py`, ni `core/audit.py`); `migrations/env.py` y las pruebas
  quedan fuera de `src/app`.
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._imports import find_forbidden_imports

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
WORKER = SRC / "worker"
CLI = SRC / "cli.py"
MODULO_AJENO = "__capa_de_aplicacion__"
"""Nombre de módulo que no existe: así todo `models`/`router`/privado de un módulo es ajeno."""

SQL_LLAMADAS = frozenset({"text", "exec_driver_sql"})


def _archivos_de_aplicacion() -> list[Path]:
    return [*sorted(WORKER.rglob("*.py")), CLI]


def _violaciones_de_imports(path: Path, fuente: str | None = None) -> list[str]:
    return [str(v) for v in find_forbidden_imports(path, module=MODULO_AJENO, source=fuente)]


def llamadas_sql(fuente: str, nombre: str) -> list[str]:
    """`text(...)`, `sa.text(...)` o `x.exec_driver_sql(...)` en `fuente`."""
    arbol = ast.parse(fuente, filename=nombre)
    salida: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        llamada = (
            funcion.id
            if isinstance(funcion, ast.Name)
            else funcion.attr
            if isinstance(funcion, ast.Attribute)
            else None
        )
        if llamada in SQL_LLAMADAS:
            salida.append((nodo.lineno, f"{nombre}:{nodo.lineno} {llamada}("))
    return [texto for _, texto in sorted(salida)]


def _modulo_de(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("").as_posix().replace("/", ".")
    return "app." + rel.removesuffix(".__init__")


def importa_core_jobs(fuente: str, path: Path) -> list[int]:
    """Líneas de `fuente` (archivo `path` bajo `src/app`) que importan `app.core.jobs`."""
    arbol = ast.parse(fuente, filename=str(path))
    paquete = _modulo_de(path).rsplit(".", 1)[0] if path.name != "__init__.py" else _modulo_de(path)
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            if any(
                a.name == "app.core.jobs" or a.name.startswith("app.core.jobs.") for a in nodo.names
            ):
                lineas.append(nodo.lineno)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            if nodo.level:
                partes = paquete.split(".")
                partes = partes[: len(partes) - (nodo.level - 1)]
                base = ".".join([*partes, base] if base else partes)
            if base == "app.core.jobs" or base.startswith("app.core.jobs."):
                lineas.append(nodo.lineno)
            elif base == "app.core" and any(a.name == "jobs" for a in nodo.names):
                lineas.append(nodo.lineno)
    return lineas


# Reglas sobre el árbol real -------------------------------------------------------------------


def test_el_worker_existe_y_tiene_archivos_que_revisar() -> None:
    nombres = {p.relative_to(WORKER).as_posix() for p in WORKER.rglob("*.py")}
    esperados = {
        "__init__.py",
        "schedule.py",
        "registry.py",
        "runner.py",
        "runtime.py",
        "main.py",
        "jobs/__init__.py",
        "jobs/expirations.py",
    }
    assert esperados <= nombres, sorted(esperados - nombres)


def test_worker_y_cli_no_importan_models_router_ni_privados() -> None:
    violaciones = [v for p in _archivos_de_aplicacion() for v in _violaciones_de_imports(p)]
    assert violaciones == []


def test_el_worker_no_escribe_sql() -> None:
    hallazgos = [
        h
        for p in sorted(WORKER.rglob("*.py"))
        for h in llamadas_sql(p.read_text(encoding="utf-8"), p.relative_to(SRC).as_posix())
    ]
    assert hallazgos == []


def test_solo_el_worker_importa_core_jobs() -> None:
    importadores = sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p != SRC / "core" / "jobs.py" and importa_core_jobs(p.read_text(encoding="utf-8"), p)
    )
    fuera = [nombre for nombre in importadores if not nombre.startswith("worker/")]
    assert fuera == []
    assert importadores, "ningún archivo del worker importa app.core.jobs"


# Controles con fuentes falsas ------------------------------------------------------------------


def test_control_imports_prohibidos_se_detectan() -> None:
    falsa = (
        "from app.modules.plans.models import Plan\n"
        "from app.modules.members import router\n"
        "from app.modules.auth import tokens\n"
        "from app.modules.memberships.lifecycle import algo\n"
        "def f():\n"
        "    from app.modules.payments.models import Payment\n"
        "from app.modules.plans import service\n"
        "from app.modules.plans.schemas import PlanCreate\n"
        "from app.modules.payments.exceptions import PaymentError\n"
    )
    violaciones = _violaciones_de_imports(WORKER / "jobs" / "falso.py", falsa)
    reglas = sorted(v.rsplit("(", 1)[1].rstrip(")") for v in violaciones)
    assert reglas == [
        "foreign_models",
        "foreign_models",
        "foreign_router",
        "private_helper",
        "private_helper",
    ]


def test_control_sql_literal_se_detecta() -> None:
    falsa = (
        "import sqlalchemy as sa\n"
        "from sqlalchemy import text\n"
        "async def f(s, c):\n"
        "    await s.execute(text('SELECT 1'))\n"
        "    await s.execute(sa.text('SELECT 2'))\n"
        "    await c.exec_driver_sql('SELECT 3')\n"
        "    ruta.write_text('no es sql')\n"
    )
    assert llamadas_sql(falsa, "worker/falso.py") == [
        "worker/falso.py:4 text(",
        "worker/falso.py:5 text(",
        "worker/falso.py:6 exec_driver_sql(",
    ]


def test_control_importadores_de_core_jobs_se_detectan() -> None:
    assert importa_core_jobs("from app.core import jobs\n", SRC / "main.py") == [1]
    assert importa_core_jobs("from app.core.jobs import claim_run\n", SRC / "main.py") == [1]
    assert importa_core_jobs("import app.core.jobs\n", SRC / "core" / "health.py") == [1]
    assert importa_core_jobs("from . import jobs\n", SRC / "core" / "audit.py") == [1]
    assert importa_core_jobs("from .jobs import last_run\n", SRC / "core" / "health.py") == [1]
    perezoso = "def f():\n    from app.core.jobs import last_run\n"
    assert importa_core_jobs(perezoso, SRC / "core" / "health.py") == [2]
    assert importa_core_jobs("from app.core import clock\n", SRC / "main.py") == []
