"""Nadie en `app/` apaga ni salta los triggers de inmutabilidad (S3-B1; M-6, S3-D49, S3-D69).

Las tablas inmutables (`audit.audit_log`, `crypto.crypto_ops`, `memberships.memberships` desde
`0008` y `payments.payments` desde `0011`) se protegen con triggers `ENABLE ALWAYS`. El rol de la
aplicación es dueño de las tablas (la separación de roles llega en S4B-W0-2): si una cadena del api
pudiera ejecutar `DISABLE TRIGGER`, `session_replication_role = replica`, `ALTER TABLE ... TRIGGER`
o vaciar una tabla, el trigger no protegería nada. Regla: ninguna cadena de `src/app` (incluidos
docstrings, comentarios no cuentan porque no son cadenas) contiene esas palabras; solo
`migrations/` y `tests/` pueden.

La palabra de vaciar tablas se busca en mayúsculas (como se escribe el SQL del repo) o, en
cualquier caso, seguida de una tabla con esquema (`truncate [table] esquema.tabla`), para no
confundirla con el helper `auth.rules.truncate`, que corta texto.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
APP = SRC / "app"

PATRONES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DISABLE TRIGGER", re.compile(r"\bdisable\s+trigger\b", re.IGNORECASE)),
    ("session_replication_role", re.compile(r"session_replication_role", re.IGNORECASE)),
    ("ALTER TABLE ... TRIGGER", re.compile(r"\balter\s+table\b[^;]*\btrigger\b", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\b")),
    ("TRUNCATE", re.compile(r"\btruncate\s+(table\s+)?[a-z_]+\.[a-z_]+", re.IGNORECASE)),
)


def hallazgos(fuente: str, archivo: str) -> list[str]:
    """`archivo:línea: patrón` por cada cadena que contiene un patrón prohibido."""
    salida: list[str] = []
    for nodo in ast.walk(ast.parse(fuente, filename=archivo)):
        if not (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)):
            continue
        for nombre, patron in PATRONES:
            if patron.search(nodo.value):
                salida.append(f"{archivo}:{nodo.lineno}: {nombre}")
                break
    return salida


def test_hay_archivos_que_revisar() -> None:
    assert len(list(APP.rglob("*.py"))) > 50


def test_ninguna_cadena_de_app_apaga_ni_salta_triggers() -> None:
    encontrados = [
        h
        for path in sorted(APP.rglob("*.py"))
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], "\n".join(encontrados)


# Controles con fuentes falsas ----------------------------------------------------------------

FALSAS = {
    "sql": 'text("ALTER TABLE payments.payments DISABLE TRIGGER USER")\n',
    "replica": 'await s.execute(text("SET session_replication_role = replica"))\n',
    "alter-trigger": 'SQL = "ALTER TABLE memberships.memberships ENABLE TRIGGER USER"\n',
    "vaciar-mayusculas": '"""Borra todo con TRUNCATE si hace falta."""\n',
    "vaciar-minusculas": 'q = "truncate table payments.payments"\n',
    "vaciar-esquema": 'q = "truncate memberships.memberships"\n',
    "f-string": 'f"ALTER TABLE {t} DISABLE TRIGGER {n}"\n',
}


def test_cada_fuente_falsa_se_detecta() -> None:
    for nombre, fuente in FALSAS.items():
        assert hallazgos(fuente, f"{nombre}.py"), nombre


def test_una_fuente_limpia_pasa() -> None:
    limpia = (
        '"""Inmutable: el trigger rechaza cambios y borrados."""\n'
        "from app.modules.auth.rules import truncate\n"
        'agente = truncate("Mozilla/5.0", 10)\n'
        '"""`truncate(value, limit)` corta texto."""\n'
        'SQL = "SELECT pg_advisory_xact_lock(hashtextextended(:m, 0))"\n'
    )
    assert hallazgos(limpia, "limpia.py") == []


def test_audit_sign_esta_barrido_y_no_apaga_triggers() -> None:
    """S6-A1: `core/audit_sign.py` (tabla append-only con `signatures_forbid_*`) existe y está
    dentro del barrido de `app/`; ninguna de sus cadenas apaga o salta triggers."""
    path = APP / "core" / "audit_sign.py"
    assert path.is_file()
    assert hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix()) == []


def test_attachments_esta_barrido_y_no_apaga_triggers() -> None:
    """S6-C1: el módulo de adjuntos (tabla con `attachments_guard_update`, `attachments_forbid_*`)
    existe, está dentro del barrido de `app/` y ninguna de sus cadenas apaga o salta triggers."""
    carpeta = APP / "modules" / "attachments"
    archivos = sorted(carpeta.rglob("*.py"))
    assert (carpeta / "service.py").is_file() and archivos
    encontrados = [
        h
        for path in archivos
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], "\n".join(encontrados)


def test_classes_esta_barrido_y_no_apaga_triggers() -> None:
    """S7-B1: el módulo de clases (tablas con `class_*_forbid_*` y `class_sessions_guard_update`)
    existe, está dentro del barrido de `app/` y ninguna de sus cadenas apaga o salta triggers."""
    carpeta = APP / "modules" / "classes"
    archivos = sorted(carpeta.rglob("*.py"))
    assert (carpeta / "sessions.py").is_file() and archivos
    encontrados = [
        h
        for path in archivos
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], "\n".join(encontrados)


def test_results_esta_barrido_y_no_apaga_triggers() -> None:
    """S8-B1: el módulo de resultados (cinco guardas de `0037`, una diferida) está dentro del
    barrido de `app/` y ninguna de sus cadenas apaga o salta triggers."""
    carpeta = APP / "modules" / "results"
    archivos = sorted(carpeta.rglob("*.py"))
    assert (carpeta / "record.py").is_file() and archivos
    encontrados = [
        h
        for path in archivos
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], "\n".join(encontrados)


def test_athletes_esta_barrido_y_no_apaga_triggers() -> None:
    """S9-A1: el módulo de medidas (cuatro guardas de `0042`) está dentro del barrido de `app/` y
    ninguna de sus cadenas apaga o salta triggers."""
    carpeta = APP / "modules" / "athletes"
    archivos = sorted(carpeta.rglob("*.py"))
    assert (carpeta / "metrics.py").is_file() and archivos
    encontrados = [
        h
        for path in archivos
        for h in hallazgos(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())
    ]
    assert encontrados == [], chr(10).join(encontrados)
