"""`core/backup_status.py` solo lee (S4B-B2; S4B-D71 / L-3, S4B-D26).

Por AST sobre `src/app/core/backup_status.py`:
- de `app.core.jobs` importa un solo nombre, `last_run`, en una sola sentencia `from ... import`;
  ni `import app.core.jobs`, ni `from app.core import jobs`, ni `*`;
- no contiene llamadas `insert(`, `update(`, `delete(` ni `commit`/`flush`/`rollback`, ni candados
  (`with_for_update`, `lock_member`, `pg_advisory`): `/health` es público y no escribe ni bloquea;
- tampoco `text(` ni `execute(` directos: todo SQL vive en `core/jobs.py`.
`worker/jobs/backup_check.py` tampoco pide candados nuevos (los toma solo el runner al reclamar).
Controles con fuentes falsas: cada regla debe fallar ante su violación.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
BACKUP_STATUS: Final = SRC / "core" / "backup_status.py"
BACKUP_CHECK: Final = SRC / "worker" / "jobs" / "backup_check.py"
ESCRITURAS: Final = frozenset({"insert", "update", "delete", "commit", "flush", "rollback"})
SQL_DIRECTO: Final = frozenset({"text", "execute", "exec_driver_sql"})
CANDADOS: Final = frozenset(
    {
        "with_for_update",
        "lock_member",
        "lock_membership",
        "pg_advisory_lock",
        "pg_try_advisory_lock",
    }
)


def imports_de_jobs(fuente: str) -> list[list[str]]:
    """Los nombres importados de `app.core.jobs` por sentencia; `["<modulo>"]` si es `import x`."""
    salida: list[list[str]] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.ImportFrom):
            if nodo.module == "app.core.jobs":
                salida.append([a.name for a in nodo.names])
            elif nodo.module == "app.core" and any(a.name == "jobs" for a in nodo.names):
                salida.append(["<modulo jobs>"])
        elif isinstance(nodo, ast.Import):
            salida.extend(
                ["<modulo jobs>"] for a in nodo.names if a.name.startswith("app.core.jobs")
            )
    return salida


def llamadas(fuente: str, nombres: frozenset[str]) -> list[str]:
    """Nombres de `nombres` llamados como función o método en `fuente`."""
    encontrados: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        nombre = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if nombre in nombres:
            encontrados.append(nombre)
    return sorted(encontrados)


def _fuente(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# Reglas sobre el árbol real -------------------------------------------------------------------


def test_backup_status_importa_de_core_jobs_solo_last_run() -> None:
    assert imports_de_jobs(_fuente(BACKUP_STATUS)) == [["last_run"]]


def test_backup_status_no_escribe_ni_confirma() -> None:
    fuente = _fuente(BACKUP_STATUS)
    assert llamadas(fuente, ESCRITURAS) == []
    assert "commit" not in fuente


def test_backup_status_no_escribe_sql_directo_ni_pide_candados() -> None:
    fuente = _fuente(BACKUP_STATUS)
    assert llamadas(fuente, SQL_DIRECTO) == []
    assert llamadas(fuente, CANDADOS) == []


def test_backup_check_no_escribe_sql_ni_pide_candados() -> None:
    fuente = _fuente(BACKUP_CHECK)
    assert llamadas(fuente, SQL_DIRECTO) == []
    assert llamadas(fuente, CANDADOS) == []
    assert llamadas(fuente, frozenset({"insert", "delete", "commit"})) == []


def test_backup_check_lee_la_racha_solo_con_last_results_de_core_jobs() -> None:
    nombres = [n for sentencia in imports_de_jobs(_fuente(BACKUP_CHECK)) for n in sentencia]
    assert nombres == ["last_results"]


# Controles con fuentes falsas ------------------------------------------------------------------


def test_control_imports_de_core_jobs_se_ven() -> None:
    assert imports_de_jobs("from app.core.jobs import last_run\n") == [["last_run"]]
    assert imports_de_jobs("from app.core.jobs import last_run, claim_run\n") == [
        ["last_run", "claim_run"]
    ]
    assert imports_de_jobs("from app.core import jobs\n") == [["<modulo jobs>"]]
    assert imports_de_jobs("import app.core.jobs\n") == [["<modulo jobs>"]]
    assert imports_de_jobs("from app.core.jobs import *\n") == [["*"]]
    assert imports_de_jobs("from app.core.clock import current_clock\n") == []


def test_control_escrituras_sql_y_candados_se_ven() -> None:
    falsa = (
        "async def f(s):\n"
        "    await s.execute(insert(X).values(a=1))\n"
        "    await s.execute(update(X))\n"
        "    await s.execute(delete(X))\n"
        "    await s.commit()\n"
        "    await s.execute(text('SELECT 1'))\n"
        "    q = select(X).with_for_update()\n"
        "    await lock_member(s, 1)\n"
    )
    assert llamadas(falsa, ESCRITURAS) == ["commit", "delete", "insert", "update"]
    assert llamadas(falsa, SQL_DIRECTO) == ["execute", "execute", "execute", "execute", "text"]
    assert llamadas(falsa, CANDADOS) == ["lock_member", "with_for_update"]
    assert llamadas("x = a.b\n", ESCRITURAS | SQL_DIRECTO | CANDADOS) == []
