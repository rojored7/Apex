"""Módulos de lectura (S4A-B8; S4A-D27, S4A-D28; C9).

`dashboard` solo compone services de otros módulos:
- no tiene `models.py` (ni tablas propias);
- ningún archivo importa `app.modules.<m>.models`, `app.core.audit` ni `app.core.audit_verify`
  (la cadena se lee por `audit.service.recent`, nunca directo);
- ningún archivo contiene `session.execute(` (ni otra forma de SQL: `.execute(`, `.scalar(`,
  `.scalars(`, `text(`), y no se suscribe a eventos (`subscribe`): `SUSCRIPTORES_ESPERADOS` de
  `test_handlers_no_new_locks.py` no cambia.
Los controles con fuente falsa prueban que el detector ve cada forma.
"""

from __future__ import annotations

import ast
from importlib.util import find_spec
from pathlib import Path
from typing import Final

import app

MODULES_DIR: Final = Path(app.__file__).resolve().parent / "modules"
MODULOS_DE_LECTURA: Final = ("dashboard",)
NUCLEO_PROHIBIDO: Final = frozenset({"app.core.audit", "app.core.audit_verify"})
LLAMADAS_SQL: Final = frozenset({"execute", "scalar", "scalars", "stream", "text"})


def _modulo_importado(nodo: ast.Import | ast.ImportFrom, modulo: str) -> list[str]:
    if isinstance(nodo, ast.Import):
        return [alias.name for alias in nodo.names]
    if nodo.level:
        base = {1: f"app.modules.{modulo}", 2: "app.modules"}.get(nodo.level, "")
        origen = f"{base}.{nodo.module}" if nodo.module else base
    else:
        origen = nodo.module or ""
    return [origen, *(f"{origen}.{alias.name}" for alias in nodo.names)]


def _es_models(nombre: str) -> bool:
    partes = nombre.split(".")
    return nombre.startswith("app.modules.") and len(partes) >= 4 and partes[3] == "models"


def violaciones(fuente: str, modulo: str) -> list[str]:
    """`"<motivo>:<línea>"` por cada import prohibido, SQL o suscripción en `fuente`."""
    halladas: list[str] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import | ast.ImportFrom):
            for nombre in _modulo_importado(nodo, modulo):
                if _es_models(nombre):
                    halladas.append(f"models {nombre}:{nodo.lineno}")
                if nombre in NUCLEO_PROHIBIDO:
                    halladas.append(f"core {nombre}:{nodo.lineno}")
        elif isinstance(nodo, ast.Call):
            llamado = nodo.func
            nombre = (
                llamado.attr
                if isinstance(llamado, ast.Attribute)
                else llamado.id
                if isinstance(llamado, ast.Name)
                else None
            )
            if nombre in LLAMADAS_SQL:
                halladas.append(f"sql {nombre}:{nodo.lineno}")
            if nombre == "subscribe":
                halladas.append(f"subscribe:{nodo.lineno}")
    return sorted(set(halladas))


def _archivos(modulo: str) -> list[Path]:
    return sorted((MODULES_DIR / modulo).rglob("*.py"))


def test_dashboard_existe_y_no_tiene_models() -> None:
    for modulo in MODULOS_DE_LECTURA:
        assert (MODULES_DIR / modulo / "service.py").is_file(), modulo
        assert (MODULES_DIR / modulo / "router.py").is_file(), modulo
        assert not (MODULES_DIR / modulo / "models.py").exists(), modulo
        assert find_spec(f"app.modules.{modulo}.models") is None, modulo


def test_dashboard_no_importa_models_ni_la_cadena_ni_ejecuta_sql() -> None:
    malas = [
        f"{archivo.relative_to(MODULES_DIR).as_posix()}: {v}"
        for modulo in MODULOS_DE_LECTURA
        for archivo in _archivos(modulo)
        for v in violaciones(archivo.read_text(encoding="utf-8"), modulo)
    ]
    assert malas == [], "\n".join(malas)


def test_dashboard_no_contiene_session_execute_en_texto() -> None:
    """Respaldo textual de la regla de S4A-D28 (también en comentarios o cadenas)."""
    con_execute = [
        archivo.name
        for modulo in MODULOS_DE_LECTURA
        for archivo in _archivos(modulo)
        if "session.execute(" in archivo.read_text(encoding="utf-8")
    ]
    assert con_execute == []


# Controles del detector --------------------------------------------------------------------

FUENTE_MALA = """
from app.modules.members.models import Member
from app.modules.payments import models
from ..memberships.models import Membership
import app.core.audit
from app.core.audit_verify import AuditVerification
from sqlalchemy import text

async def f(session):
    await session.execute(text("SELECT 1"))
    await session.scalar(None)
    events.subscribe(Algo, f)
"""

FUENTE_BUENA = """
from app.modules.audit import service as audit_service
from app.modules.members import service as members_service
from app.modules.dashboard.schemas import DashboardOut

async def f(session):
    return await audit_service.recent(session, ("members.members",), 10)
"""


def test_el_detector_ve_models_nucleo_sql_y_suscripciones() -> None:
    motivos = [v.split(":")[0] for v in violaciones(FUENTE_MALA, "dashboard")]
    assert sum(m.startswith("models ") for m in motivos) >= 3, motivos
    assert "core app.core.audit" in motivos
    assert "core app.core.audit_verify" in motivos
    assert {"sql execute", "sql scalar", "sql text", "subscribe"} <= set(motivos)


def test_el_detector_acepta_services_y_schemas() -> None:
    assert violaciones(FUENTE_BUENA, "dashboard") == []
