"""El módulo `audit` (S2-B6; US-107; riesgo 6.10, decisión 21; CLAUDE.md, reglas de módulos).

- `MODULES == ("auth", "settings", "audit", "members", "plans", "memberships", "payments")`:
  `audit` va después de `auth`, cuyo `service.py` declara los eventos que escucha; S2-B7 agrega
  `members`, S2-B9 `plans`, S3-B1 `memberships` y S3-B3 `payments` al final (D1 del Sprint 3:
  la tupla final de v0.1).
- `load_module_services()` deja suscritos los cuatro handlers de `audit.service` a sus eventos,
  una sola vez cada uno (se compara por identidad de función).
- `modules/audit` tiene `router.py` (desde S4A-B3 con `POST /audit/verify` y
  `GET /audit/verify/last`, y `no_store`), `service.py` y ningún `models.py` (las tablas viven en
  `core/audit.py` y `core/audit_verify.py`); importa de `auth` solo `service.py` (las clases
  de evento), nunca sus
  `models.py`, `router.py` ni helpers privados.
- `auth` no importa nada de `audit` (el sentido es `audit → auth`).
"""

from __future__ import annotations

import ast
import importlib
from importlib.util import find_spec
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

import app
from app.core import events
from app.core.http import no_store
from app.main import MODULES, load_module_services
from app.modules.auth.service import (
    LoginAttempted,
    PasswordChanged,
    SessionsRevoked,
    UserLocked,
)
from tests.architecture._imports import find_forbidden_imports

MODULES_DIR = Path(app.__file__).resolve().parent / "modules"
HANDLERS = (
    (LoginAttempted, "on_login_attempted"),
    (UserLocked, "on_user_locked"),
    (SessionsRevoked, "on_sessions_revoked"),
    (PasswordChanged, "on_password_changed"),
)


def test_modules_de_v01_incluye_audit_despues_de_auth() -> None:
    """S2-B7 suma `members`, S2-B9 `plans`, S3-B1 `memberships` y S3-B3 `payments` al final (D1 del
    Sprint 3: `memberships` antes que `payments`; tupla final de v0.1)."""
    assert MODULES == (
        "auth",
        "settings",
        "audit",
        "members",
        "plans",
        "memberships",
        "payments",
    )


@pytest.mark.parametrize(("evento", "nombre"), HANDLERS, ids=[n for _, n in HANDLERS])
def test_load_module_services_suscribe_cada_handler_una_vez(
    evento: type[events.DomainEvent], nombre: str
) -> None:
    load_module_services()
    audit_service = importlib.import_module("app.modules.audit.service")
    handler = getattr(audit_service, nombre)
    suscritos = events.subscribers_for(evento)
    assert sum(1 for h in suscritos if h is handler) == 1, (nombre, suscritos)


def test_audit_publica_verify_y_sigue_sin_models() -> None:
    """S4A-B3 (S4A-D14, S4A-D18): el router de `audit` tiene exactamente `POST /audit/verify` y
    `GET /audit/verify/last` (B4 sumará la lista y el detalle), lleva `no_store` en el `APIRouter`
    y el módulo sigue sin `models.py` (`AuditVerification` vive en `core/audit_verify.py`)."""
    router = importlib.import_module("app.modules.audit.router").router
    rutas = {
        (metodo, ruta.path)
        for ruta in router.routes
        if isinstance(ruta, APIRoute)
        for metodo in ruta.methods
    }
    assert rutas == {("POST", "/audit/verify"), ("GET", "/audit/verify/last")}
    assert any(d.dependency is no_store for d in router.dependencies)
    assert find_spec("app.modules.audit.service") is not None
    assert find_spec("app.modules.audit.models") is None


def test_audit_no_importa_models_router_ni_helpers_de_otros_modulos() -> None:
    violaciones = [
        str(v)
        for archivo in sorted((MODULES_DIR / "audit").rglob("*.py"))
        for v in find_forbidden_imports(archivo, module="audit")
    ]
    assert violaciones == [], "\n".join(violaciones)


def _importados(archivo: Path) -> list[str]:
    nombres: list[str] = []
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))):
        if isinstance(nodo, ast.Import):
            nombres.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                # Dentro de `app/modules/auth/`: nivel 2 es `app.modules`.
                base = "app.modules" if nodo.level == 2 else "app.modules.auth"
                modulo = f"{base}.{nodo.module}" if nodo.module else base
            else:
                modulo = nodo.module or ""
            nombres.append(modulo)
            nombres.extend(f"{modulo}.{alias.name}" for alias in nodo.names)
        elif (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "import_module"
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
            and isinstance(nodo.args[0].value, str)
        ):
            nombres.append(nodo.args[0].value)
    return nombres


def test_auth_no_importa_nada_de_audit() -> None:
    violaciones = [
        f"{archivo.relative_to(MODULES_DIR)}: {nombre}"
        for archivo in sorted((MODULES_DIR / "auth").rglob("*.py"))
        for nombre in _importados(archivo)
        if nombre == "app.modules.audit" or nombre.startswith("app.modules.audit.")
    ]
    assert violaciones == [], "\n".join(violaciones)


def test_el_analizador_detecta_un_import_de_audit_desde_auth(tmp_path: Path) -> None:
    """Control de la prueba anterior: el recorrido ve imports absolutos, relativos y perezosos."""
    archivo = tmp_path / "service.py"
    archivo.write_text(
        "from app.modules.audit import service\n"
        "from ..audit.service import on_user_locked\n"
        "def f():\n"
        "    import importlib\n"
        "    importlib.import_module('app.modules.audit.service')\n",
        encoding="utf-8",
    )
    nombres = [n for n in _importados(archivo) if n.startswith("app.modules.audit")]
    assert "app.modules.audit" in nombres
    assert "app.modules.audit.service.on_user_locked" in nombres
    assert nombres.count("app.modules.audit.service") >= 2
