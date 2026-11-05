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


def test_jobs_y_alerts_no_importan_modulos_ni_audit() -> None:
    """S4A-B1 (S4A-D3, S4A-D7, S4A-D73): `core/jobs.py` y `core/alerts.py` no importan
    `app.modules` ni `app.core.audit`; `core/audit.py` y `core/health.py` no importan
    `app.core.jobs` (ni perezoso). Los dos archivos deben existir: sin ellos la regla no vigila."""
    violaciones: list[str] = []
    for nombre in ("jobs.py", "alerts.py"):
        path = CORE / nombre
        assert path.is_file(), f"falta core/{nombre}"
        violaciones += [
            f"{nombre}: {n}"
            for n in _imports(path)
            if n.startswith(("app.modules", "app.core.audit"))
        ]
    for nombre in ("audit.py", "health.py"):
        violaciones += [
            f"{nombre}: {n}"
            for n in _imports(CORE / nombre)
            if n == "app.core.jobs" or n.startswith("app.core.jobs.")
        ]
        violaciones += _desde_core_importa_jobs(CORE / nombre)
    assert violaciones == []


def _desde_core_importa_jobs(path: Path) -> list[str]:
    """`from app.core import jobs` (o `from . import jobs`) dentro de `path`."""
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path.name}:{nodo.lineno}: from {nodo.module or '.'} import jobs"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and (nodo.module == "app.core" or (nodo.level == 1 and nodo.module is None))
        and any(a.name == "jobs" for a in nodo.names)
    ]


def test_backup_status_solo_importa_jobs_db_y_clock_de_la_aplicacion() -> None:
    """S4B-B2 (S4B-D26): `core/backup_status.py` solo importa `core.jobs`, `core.db` y
    `core.clock`; no `app.modules`, ni `core.audit`, ni `core.health`, ni `core.crypto`."""
    path = CORE / "backup_status.py"
    assert path.is_file(), "falta core/backup_status.py"
    propios = sorted({n for n in _imports(path) if n.startswith("app")})
    assert set(propios) <= {"app.core.jobs", "app.core.db", "app.core.clock"}, propios
    assert "app.core.jobs" in propios, "backup_status no lee core.jobs"


def test_audit_health_y_main_no_importan_core_jobs() -> None:
    """S4B-B2: la excepción de `core.jobs` es solo `core/backup_status.py`; `core/audit.py`,
    `core/health.py` y `main.py` siguen sin importarlo (ni perezoso, ni como `from app.core import
    jobs`). `main.py` registra el check `backup` importando `backup_status`, no `core.jobs`."""
    violaciones: list[str] = []
    for path in (CORE / "audit.py", CORE / "health.py", SRC / "main.py"):
        violaciones += [
            f"{path.name}: {n}"
            for n in _imports(path)
            if n == "app.core.jobs" or n.startswith("app.core.jobs.")
        ]
        violaciones += _desde_core_importa_jobs(path)
    assert violaciones == []
    assert "app.core.backup_status" in _imports(SRC / "main.py")


PROHIBIDOS_DEL_RESPALDO_DE_KEK = ("app.core.audit", "app.modules")


def _prohibidos_en(fuente: str) -> list[str]:
    arbol = ast.parse(fuente)
    nombres: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
    return [n for n in nombres if n.startswith(PROHIBIDOS_DEL_RESPALDO_DE_KEK)]


def test_kek_backup_y_archive_no_importan_audit_ni_modules() -> None:
    """S4B-B3a (S4B-D58, S4B-D62): `kek_backup.py` y `archive.py` son de `core/crypto`; la
    auditoría de `export-kek` la escribe el CLI (`cli_ops/kek.py`), no estos archivos."""
    for nombre in ("kek_backup.py", "archive.py"):
        path = CORE / "crypto" / nombre
        assert path.is_file(), f"falta core/crypto/{nombre}"
        assert _prohibidos_en(path.read_text(encoding="utf-8")) == [], nombre


def test_control_un_import_de_audit_o_modules_en_kek_backup_se_detecta() -> None:
    assert _prohibidos_en("from app.core.audit import record\n") == ["app.core.audit"]
    assert _prohibidos_en("def f():\n    from app.modules.auth.service import x\n") == [
        "app.modules.auth.service"
    ]
    assert _prohibidos_en("from app.core.crypto.digest import sha256_hex\n") == []


# S4B-B3b: `service.py` y `discovery.py` no importan auditoría ni módulos (S4B-D39) ------------


def test_service_y_discovery_no_importan_audit_ni_modules() -> None:
    """La auditoría de `rotate-key` y `retire-key` la escribe el CLI, no `core/crypto`. Los dos
    archivos existen: sin ellos la regla no vigila."""
    for nombre in ("service.py", "discovery.py"):
        path = CORE / "crypto" / nombre
        assert path.is_file(), f"falta core/crypto/{nombre}"
        assert _prohibidos_en(path.read_text(encoding="utf-8")) == [], nombre


def test_control_service_con_audit_o_modules_se_detecta() -> None:
    falsa = (
        "from app.core.audit import record\n"
        "async def retire_key():\n"
        "    from app.modules.members.service import reveal\n"
    )
    assert _prohibidos_en(falsa) == ["app.core.audit", "app.modules.members.service"]
    assert (
        _prohibidos_en(
            "from app.core.crypto import oplog\nfrom app.core.clock import current_clock\n"
        )
        == []
    )


# S4B-B4: `core/migrations_status.py` (S4B-D27, S4B-D60) ---------------------------------------

PROHIBIDOS_DE_MIGRATIONS_STATUS = ("app.main", "app.modules", "app.core.audit", "app.core.jobs")


def _prohibidos_de_migrations(fuente: str) -> list[str]:
    arbol = ast.parse(fuente)
    nombres: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.append(nodo.module)
            if nodo.module == "app":
                nombres.extend(f"app.{a.name}" for a in nodo.names)
    return [n for n in nombres if n.startswith(PROHIBIDOS_DE_MIGRATIONS_STATUS)]


def test_migrations_status_no_importa_main_ni_modulos() -> None:
    """`main.py` calcula `head` y `known` y los entrega con `configure_migrations`; el archivo
    nunca importa `app.main` (ni perezoso), ni `app.modules`, ni auditoría ni jobs."""
    path = CORE / "migrations_status.py"
    assert path.is_file(), "falta core/migrations_status.py"
    assert _prohibidos_de_migrations(path.read_text(encoding="utf-8")) == []


def test_control_main_o_modulos_en_migrations_status_se_detectan() -> None:
    assert _prohibidos_de_migrations("from app.main import alembic_config\n") == ["app.main"]
    assert _prohibidos_de_migrations("def f():\n    import app.main\n") == ["app.main"]
    assert _prohibidos_de_migrations("from app import main\n") == ["app.main"]
    assert _prohibidos_de_migrations("from app.modules.auth import service\n") == [
        "app.modules.auth"
    ]
    assert _prohibidos_de_migrations("from app.core.db import get_sessionmaker\n") == []


# S5-B1: el proveedor de OpenBao y el puerto no tocan audit, módulos ni la capa de aplicación ----

ARCHIVOS_B1 = (
    "openbao_provider.py",
    "provider.py",
    "local_provider.py",
    "keyring.py",
    "bootstrap.py",
)


def _prohibidos_b1(fuente: str) -> list[str]:
    arbol = ast.parse(fuente)
    nombres = [n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module]
    nombres += [a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names]
    return [
        n for n in nombres if n.startswith(("app.core.audit", "app.modules", "app.cli", "app.main"))
    ]


def test_openbao_provider_existe_y_core_crypto_no_importa_audit() -> None:
    assert (CORE / "crypto" / "openbao_provider.py").is_file()
    for nombre in ARCHIVOS_B1:
        ruta = CORE / "crypto" / nombre
        assert _prohibidos_b1(ruta.read_text(encoding="utf-8")) == [], nombre


def test_control_un_import_de_audit_en_el_proveedor_se_detecta() -> None:
    assert _prohibidos_b1("from app.core.audit import write\n") == ["app.core.audit"]
    assert _prohibidos_b1("import app.core.audit\n") == ["app.core.audit"]
    assert _prohibidos_b1("def f():\n    from app.modules.members import service\n")
    assert _prohibidos_b1("from app.core.crypto.errors import CryptoError\n") == []


# S5-B3: `core/errors.py` mapea `CryptoUnavailable` y solo importa `core/crypto/errors` ----------


def test_s5_b3_errors_solo_importa_crypto_errors_de_core_crypto() -> None:
    """El handler de `CryptoUnavailable` (S5-D14) necesita el tipo, nada más del bus: ni el
    keyring, ni el proveedor, ni `recovery`. Importa `app.core.crypto.errors` (en el módulo o
    perezoso) y ningún otro `app.core.crypto.*`."""
    propios = {n for n in _imports(CORE / "errors.py") if n.startswith("app.core.crypto")}
    assert propios == {"app.core.crypto.errors"}, propios


def test_s5_b3_crypto_errors_no_importa_nada_de_la_aplicacion() -> None:
    """Como `errors.py` lo importa y `security -> db -> errors`, `crypto/errors.py` queda hoja."""
    assert [n for n in _imports(CORE / "crypto" / "errors.py") if n.startswith("app")] == []


def test_s5_b4_mail_y_alerts_telegram_no_importan_modulos_ni_audit() -> None:
    """S5-B4: los dos archivos existen (si no, la regla no vigila) y solo toman de la aplicación
    `core.config`, `core.alerts`, `core.validators` y `core.logging`; nunca `app.modules`,
    `core.audit`, `core.db` ni `core.crypto` (el correo y las alertas no tocan datos)."""
    violaciones: list[str] = []
    for nombre in ("mail.py", "alerts_telegram.py"):
        path = CORE / nombre
        assert path.is_file(), f"falta core/{nombre}"
        violaciones += [
            f"{nombre}: {n}"
            for n in _imports(path)
            if n.startswith(("app.modules", "app.core.audit", "app.core.db", "app.core.crypto"))
        ]
    assert violaciones == []


def test_s5_b4_ni_core_alerts_ni_el_resto_de_core_importa_alerts_telegram() -> None:
    """El sink se registra desde `main.py` y `worker/main.py` (raíces de composición): ningún
    otro archivo de `core` lo importa (`alerts.py` define el puerto, no depende del canal)."""
    importadores = [
        p.name
        for p in sorted(CORE.rglob("*.py"))
        if any(n == "app.core.alerts_telegram" for n in _imports(p))
    ]
    assert importadores == []


def test_core_pdf_solo_importa_la_biblioteca_estandar() -> None:
    """S5-B11 (S5-D65, M-11): el escritor de PDF no importa `app.*` ni terceros (`pypdf` es solo
    de pruebas; `reportlab`, `fpdf2` y `pillow` están prohibidos). Rojo B11."""
    import sys

    ruta = CORE / "pdf.py"
    assert ruta.is_file()
    ajenos = [
        n
        for n in _imports(ruta)
        if n.split(".")[0] not in sys.stdlib_module_names and n != "__future__"
    ]
    assert ajenos == []
