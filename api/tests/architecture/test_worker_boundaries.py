"""Fronteras del worker y de `cli.py` (US-113; S4A-D10, S4A-D73).

El worker es capa de aplicación como `cli.py`: de los módulos solo importa `service`, `schemas` y
`exceptions`. Se vigila por `ast` (con `find_forbidden_imports` de `_imports.py`, que
`test_no_cross_models.py` no aplica fuera de `app/modules/`):
- ningún archivo de `app/worker/**`, `cli.py`, `cli_base.py` ni `cli_ops/**` importa
  `app.modules.<x>.models`, `app.modules.<x>.router` ni un helper privado de `PRIVATE_HELPERS`;
- ningún archivo de `app/worker/**` escribe SQL: sin llamadas `text(...)` ni
  `.exec_driver_sql(...)` (todo el SQL del worker vive en `core/jobs.py` o llega por services);
- los únicos importadores de `app.core.jobs` dentro de `src/app` son archivos de `app/worker/` y,
  desde S4B-B2 (S4B-D26), `core/backup_status.py` (lectura de `/health`; enmienda acotada a ese
  archivo, ni `main.py`, ni `core/health.py`, ni `core/audit.py`); `migrations/env.py` y las
  pruebas quedan fuera de `src/app`.
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._imports import find_forbidden_imports

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
WORKER = SRC / "worker"
CLI = SRC / "cli.py"
CLI_BASE = SRC / "cli_base.py"
CLI_OPS = SRC / "cli_ops"
SEED = SRC / "seed"
IMPORTS = SRC / "imports"
MODULO_AJENO = "__capa_de_aplicacion__"
"""Nombre de módulo que no existe: así todo `models`/`router`/privado de un módulo es ajeno."""

SQL_LLAMADAS = frozenset({"text", "exec_driver_sql"})
IMPORTADORES_EXTRA_DE_CORE_JOBS = frozenset({"core/backup_status.py"})
"""Única excepción fuera de `app/worker/` (S4B-D26): una lista de un archivo, no un prefijo."""


def _archivos_de_aplicacion() -> list[Path]:
    """La capa de aplicación (S4B-D53): `worker/**`, `cli.py`, `cli_base.py`, `cli_ops/**` y,
    cuando existan (B1), `seed/**` e `imports/**`; un directorio ausente no aporta archivos."""
    carpetas = (WORKER, CLI_OPS, SEED, IMPORTS)
    return [*(p for carpeta in carpetas for p in sorted(carpeta.rglob("*.py"))), CLI, CLI_BASE]


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
        "jobs/backup_check.py",
        "jobs/notify.py",
    }
    assert esperados <= nombres, sorted(esperados - nombres)


def test_la_capa_de_aplicacion_incluye_cli_base_y_cli_ops() -> None:
    nombres = {p.relative_to(SRC).as_posix() for p in _archivos_de_aplicacion()}
    assert {"cli.py", "cli_base.py", "cli_ops/__init__.py"} <= nombres
    assert any(n.startswith("worker/") for n in nombres)


def test_la_capa_de_aplicacion_barre_seed_e_imports() -> None:
    """S4B-B1: `seed/**` e `imports/**` entran al barrido (ya existen)."""
    nombres = {p.relative_to(SRC).as_posix() for p in _archivos_de_aplicacion()}
    assert {
        "seed/__init__.py",
        "seed/dataset.py",
        "seed/apply.py",
        "imports/__init__.py",
        "imports/members_xlsx.py",
        "imports/report.py",
        "cli_ops/seed_demo.py",
        "cli_ops/import_members.py",
    } <= nombres


def test_seed_e_imports_no_escriben_sql() -> None:
    """S4B-B1: `seed/` e `imports/` solo llegan a la base por services (sin `text(...)`)."""
    hallazgos = [
        h
        for carpeta in (SEED, IMPORTS)
        for p in sorted(carpeta.rglob("*.py"))
        for h in llamadas_sql(p.read_text(encoding="utf-8"), p.relative_to(SRC).as_posix())
    ]
    assert hallazgos == []


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


def es_importador_permitido_de_core_jobs(relativo: str) -> bool:
    return relativo.startswith("worker/") or relativo in IMPORTADORES_EXTRA_DE_CORE_JOBS


def test_solo_el_worker_y_backup_status_importan_core_jobs() -> None:
    importadores = sorted(
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if p != SRC / "core" / "jobs.py" and importa_core_jobs(p.read_text(encoding="utf-8"), p)
    )
    fuera = [n for n in importadores if not es_importador_permitido_de_core_jobs(n)]
    assert fuera == []
    assert any(n.startswith("worker/") for n in importadores), (
        "ningún archivo del worker lo importa"
    )
    assert "core/backup_status.py" in importadores, "backup_status no lee core.jobs"


def test_backup_check_existe_y_no_escribe_sql() -> None:
    path = WORKER / "jobs" / "backup_check.py"
    assert path.is_file()
    assert llamadas_sql(path.read_text(encoding="utf-8"), "worker/jobs/backup_check.py") == []
    assert _violaciones_de_imports(path) == []


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


def test_control_la_excepcion_de_core_jobs_es_solo_backup_status() -> None:
    assert es_importador_permitido_de_core_jobs("worker/jobs/backup_check.py")
    assert es_importador_permitido_de_core_jobs("core/backup_status.py")
    for ajeno in (
        "core/health.py",
        "core/audit.py",
        "core/backup_status_extra.py",
        "main.py",
        "cli.py",
        "cli_ops/recompute.py",
        "modules/dashboard/service.py",
        "seed/apply.py",
    ):
        assert not es_importador_permitido_de_core_jobs(ajeno), ajeno
    # y el analizador sigue viendo la violación en un archivo ajeno
    assert importa_core_jobs("from app.core.jobs import last_run\n", SRC / "main.py") == [1]


def test_control_una_fuente_falsa_en_cli_ops_se_detecta() -> None:
    falsa = "from app.modules.members.models import Member\nfrom app.modules.auth import tokens\n"
    violaciones = _violaciones_de_imports(CLI_OPS / "falso.py", falsa)
    reglas = sorted(v.rsplit("(", 1)[1].rstrip(")") for v in violaciones)
    assert reglas == ["foreign_models", "private_helper"]


def test_control_text_en_seed_y_models_en_imports_se_detectan() -> None:
    sql = "from sqlalchemy import text\nasync def f(s):\n    await s.execute(text('SELECT 1'))\n"
    assert llamadas_sql(sql, "seed/falso.py") == ["seed/falso.py:3 text("]
    assert llamadas_sql(sql, "imports/falso.py") == ["imports/falso.py:3 text("]
    models = "from app.modules.members.models import Member\n"
    violaciones = _violaciones_de_imports(IMPORTS / "x.py", models)
    assert [v.rsplit("(", 1)[1].rstrip(")") for v in violaciones] == ["foreign_models"]
    privado = (
        "from app.modules.memberships import sell\nfrom app.modules.payments.router import r\n"
    )
    violaciones = _violaciones_de_imports(SEED / "x.py", privado)
    reglas = sorted(v.rsplit("(", 1)[1].rstrip(")") for v in violaciones)
    assert reglas == ["foreign_router", "private_helper"]


def test_la_capa_de_aplicacion_barre_cli_ops_kek() -> None:
    """S4B-B3a: `cli_ops/kek.py` entra al barrido de imports y no escribe SQL."""
    nombres = {p.relative_to(SRC).as_posix() for p in _archivos_de_aplicacion()}
    assert "cli_ops/kek.py" in nombres
    fuente = (CLI_OPS / "kek.py").read_text(encoding="utf-8")
    assert llamadas_sql(fuente, "cli_ops/kek.py") == []
    assert _violaciones_de_imports(CLI_OPS / "kek.py") == []


def test_control_models_o_router_en_cli_ops_kek_se_detectan() -> None:
    falsa = "from app.modules.auth.models import User\nfrom app.modules.members.router import r\n"
    reglas = sorted(
        v.rsplit("(", 1)[1].rstrip(")") for v in _violaciones_de_imports(CLI_OPS / "kek.py", falsa)
    )
    assert reglas == ["foreign_models", "foreign_router"]
    sql = "async def f(s):\n    await s.execute(text('SELECT 1'))\n"
    assert llamadas_sql(sql, "cli_ops/kek.py") == ["cli_ops/kek.py:2 text("]


# S4B-B3b: `rotate_key.py` y `retire_key.py` entran al barrido (S4B-D39, D86) ------------------


def test_la_capa_de_aplicacion_barre_rotate_key_y_retire_key() -> None:
    """Entran al barrido de imports, no escriben SQL y no importan `models`/`router`/privados."""
    nombres = {p.relative_to(SRC).as_posix() for p in _archivos_de_aplicacion()}
    assert {"cli_ops/rotate_key.py", "cli_ops/retire_key.py"} <= nombres
    for nombre in ("rotate_key.py", "retire_key.py"):
        path = CLI_OPS / nombre
        fuente = path.read_text(encoding="utf-8")
        assert llamadas_sql(fuente, f"cli_ops/{nombre}") == [], nombre
        assert _violaciones_de_imports(path) == [], nombre


def test_rotate_key_y_retire_key_no_importan_core_jobs() -> None:
    """Solo el worker y `core/backup_status.py` importan `core.jobs`; `retire-key` lee el
    manifiesto del volumen, no `job_runs`."""
    for nombre in ("rotate_key.py", "retire_key.py"):
        path = CLI_OPS / nombre
        assert importa_core_jobs(path.read_text(encoding="utf-8"), path) == [], nombre


def test_control_sql_o_models_en_rotate_key_se_detectan() -> None:
    falsa = (
        "from app.modules.members.models import Member\n"
        "async def f(s):\n    await s.execute(text('SELECT 1'))\n"
    )
    ruta = CLI_OPS / "rotate_key.py"
    assert llamadas_sql(falsa, "cli_ops/rotate_key.py") == ["cli_ops/rotate_key.py:3 text("]
    assert [v.rsplit("(", 1)[1].rstrip(")") for v in _violaciones_de_imports(ruta, falsa)] == [
        "foreign_models"
    ]


# S5-B8: `jobs/notify.py` y `cli_ops/notify.py` (S5-D35, S5-D97). # Rojo B8 -----------------------

NOTIFY_JOB = WORKER / "jobs" / "notify.py"
NOTIFY_CLI = CLI_OPS / "notify.py"
MODULOS_DEL_JOB_NOTIFY = frozenset({"notifications", "memberships"})
PERMITIDOS_DEL_JOB_NOTIFY = frozenset({"service", "schemas", "exceptions"})


def modulos_importados(fuente: str) -> set[tuple[str, str]]:
    """`(modulo, archivo)` de cada `from app.modules.<m>.<archivo> import ...` o
    `from app.modules.<m> import <archivo>` de `fuente` (a cualquier profundidad)."""
    salida: set[tuple[str, str]] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.ImportFrom) or not (nodo.module or "").startswith(
            "app.modules."
        ):
            continue
        partes = (nodo.module or "").split(".")[2:]
        if len(partes) >= 2:
            salida.add((partes[0], partes[1]))
        elif len(partes) == 1:
            salida.update((partes[0], a.name) for a in nodo.names)
    return salida


def test_el_job_notify_solo_importa_service_schemas_y_exceptions_de_sus_dos_modulos() -> None:
    importados = modulos_importados(NOTIFY_JOB.read_text(encoding="utf-8"))
    assert importados, "notify.py no importa nada de notifications"
    assert {m for m, _ in importados} <= MODULOS_DEL_JOB_NOTIFY, sorted(importados)
    assert {a for _, a in importados} <= PERMITIDOS_DEL_JOB_NOTIFY, sorted(importados)
    assert ("notifications", "service") in importados


def test_el_job_notify_no_escribe_sql_ni_importa_privados() -> None:
    assert llamadas_sql(NOTIFY_JOB.read_text(encoding="utf-8"), "worker/jobs/notify.py") == []
    assert _violaciones_de_imports(NOTIFY_JOB) == []


def test_el_cli_notify_reclama_por_run_job_y_no_importa_core_jobs() -> None:
    """El CLI comparte el reclamo `notify` con el worker por `runner.run_job`; `core.jobs` sigue
    siendo del worker (no se amplía `IMPORTADORES_EXTRA_DE_CORE_JOBS`)."""
    fuente = NOTIFY_CLI.read_text(encoding="utf-8")
    assert importa_core_jobs(fuente, NOTIFY_CLI) == []
    assert "run_job" in {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.Name | ast.Attribute)
    }, "cli_ops/notify.py no llama a run_job"
    assert llamadas_sql(fuente, "cli_ops/notify.py") == []
    assert _violaciones_de_imports(NOTIFY_CLI) == []


def test_control_un_job_que_importa_plans_o_un_privado_de_notifications_se_detecta() -> None:
    falsa = (
        "from app.modules.notifications.sending import send_pending\n"
        "from app.modules.plans import service\n"
        "from app.modules.notifications import service as ok\n"
    )
    assert modulos_importados(falsa) == {
        ("notifications", "sending"),
        ("plans", "service"),
        ("notifications", "service"),
    }
    reglas = [v.rsplit("(", 1)[1].rstrip(")") for v in _violaciones_de_imports(NOTIFY_JOB, falsa)]
    assert reglas == ["private_helper"]
