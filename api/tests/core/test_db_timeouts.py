"""Tiempos de espera de la base y traducción a 503 `busy` (S3-W0-2; H-3, S3-D43, S3-D67, E7).

- `server_settings_from(settings)`: los tres `DB_*_TIMEOUT_MS` como `server_settings` de asyncpg
  (`"<n>ms"`; `"0"` desactiva) y `create_engine_from` los aplica a cada conexión.
- `sqlstate_of(error)` lee `error.orig.sqlstate`; `translate_busy(error)` da `DatabaseBusy`
  (503 `busy`, `Retry-After: 1`) para 55P03, 57014 y 40P01 y `None` para cualquier otro error.
- `get_session` traduce un 55P03 lanzado dentro del cuerpo de la ruta y también uno que ocurre
  **al confirmar** (el flush del commit, en el `__aexit__` de `session.begin()`, E7).
- `migrations/env.py` crea su propio engine, sin `create_engine_from` (E7): las migraciones no
  heredan los tiempos de espera.

Las pruebas de candado usan `dos_sesiones` (commit real) y una fila de `plans.plans` creada por la
propia prueba; el `finally` revierte siempre las dos sesiones y `dos_sesiones` borra los planes.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import (
    BUSY_SQLSTATES,
    DatabaseBusy,
    configure_sessionmaker,
    create_engine_from,
    get_session,
    server_settings_from,
    sqlstate_of,
    translate_busy,
)
from app.core.errors import DomainError
from app.modules.plans.models import Plan
from tests.factories.plans import make_plan

ENV_PY = Path(__file__).resolve().parents[2] / "migrations" / "env.py"
MENSAJE_BUSY = "La base de datos está ocupada; intenta de nuevo en un momento."
LOCK_NOT_AVAILABLE = "55P03"
QUERY_CANCELED = "57014"


class _ErrorDelAdaptador(Exception):
    """Doble del error de asyncpg adaptado por SQLAlchemy: solo expone `sqlstate`."""

    def __init__(self, sqlstate: str | None) -> None:
        super().__init__(f"sqlstate {sqlstate}")
        self.sqlstate = sqlstate


def _dbapi(sqlstate: str | None, clase: type[DBAPIError] = DBAPIError) -> DBAPIError:
    return clase("SELECT 1", {}, _ErrorDelAdaptador(sqlstate))


def _sin_timeouts(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "DB_LOCK_TIMEOUT_MS": 0,
            "DB_STATEMENT_TIMEOUT_MS": 0,
            "DB_IDLE_IN_TX_TIMEOUT_MS": 0,
        }
    )


@pytest.fixture
async def motor_con_tiempos(settings_prueba: Settings) -> AsyncIterator[AsyncEngine]:
    """Engine de `create_engine_from` sobre `TEST_DATABASE_URL` (sección 2 del plan)."""
    motor = create_engine_from(settings_prueba)
    try:
        yield motor
    finally:
        await motor.dispose()


@pytest.fixture
def sesiones_de_get_session(engine: AsyncEngine) -> Iterator[None]:
    """`get_session` real (sin override) sobre el engine de la prueba; se restaura al salir."""
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        configure_sessionmaker(None)


async def _show(motor: AsyncEngine, parametro: str) -> str:
    async with motor.connect() as conexion:
        valor = await conexion.scalar(text(f"SHOW {parametro}"))
    return str(valor)


# server_settings_from y create_engine_from --------------------------------------------------


def test_server_settings_por_defecto(settings_prueba: Settings) -> None:
    assert server_settings_from(settings_prueba) == {
        "lock_timeout": "10000ms",
        "statement_timeout": "30000ms",
        "idle_in_transaction_session_timeout": "60000ms",
    }


def test_server_settings_con_ceros_desactiva(settings_prueba: Settings) -> None:
    assert server_settings_from(_sin_timeouts(settings_prueba)) == {
        "lock_timeout": "0",
        "statement_timeout": "0",
        "idle_in_transaction_session_timeout": "0",
    }


def test_server_settings_sigue_a_cada_variable(settings_prueba: Settings) -> None:
    ajustes = settings_prueba.model_copy(
        update={
            "DB_LOCK_TIMEOUT_MS": 1500,
            "DB_STATEMENT_TIMEOUT_MS": 0,
            "DB_IDLE_IN_TX_TIMEOUT_MS": 7,
        }
    )
    assert server_settings_from(ajustes) == {
        "lock_timeout": "1500ms",
        "statement_timeout": "0",
        "idle_in_transaction_session_timeout": "7ms",
    }


async def test_el_engine_de_create_engine_from_lleva_los_tres_tiempos(
    motor_con_tiempos: AsyncEngine,
) -> None:
    assert await _show(motor_con_tiempos, "lock_timeout") == "10s"
    assert await _show(motor_con_tiempos, "statement_timeout") == "30s"
    assert await _show(motor_con_tiempos, "idle_in_transaction_session_timeout") == "1min"


async def test_el_engine_sin_tiempos_los_deja_en_cero(settings_prueba: Settings) -> None:
    motor = create_engine_from(_sin_timeouts(settings_prueba))
    try:
        assert await _show(motor, "lock_timeout") == "0"
        assert await _show(motor, "statement_timeout") == "0"
    finally:
        await motor.dispose()


# sqlstate_of y translate_busy -----------------------------------------------------------------


def test_busy_sqlstates() -> None:
    assert frozenset({"55P03", "57014", "40P01"}) == BUSY_SQLSTATES


def test_database_busy_es_un_error_de_dominio_503() -> None:
    error = DatabaseBusy()
    assert isinstance(error, DomainError)
    assert (error.status, error.code, error.message) == (503, "busy", MENSAJE_BUSY)
    assert error.headers["Retry-After"] == "1"
    assert error.field is None and error.existing_id is None


@pytest.mark.parametrize("sqlstate", ["55P03", "57014", "40P01"])
def test_translate_busy_traduce_los_tres_sqlstate(sqlstate: str) -> None:
    error = _dbapi(sqlstate)
    assert sqlstate_of(error) == sqlstate
    busy = translate_busy(error)
    assert isinstance(busy, DatabaseBusy)
    assert (busy.status, busy.code, busy.headers["Retry-After"]) == (503, "busy", "1")


@pytest.mark.parametrize("sqlstate", ["23505", "23503", "42P01", "08006", None])
def test_translate_busy_ignora_cualquier_otro_sqlstate(sqlstate: str | None) -> None:
    error = _dbapi(sqlstate)
    assert sqlstate_of(error) == sqlstate
    assert translate_busy(error) is None


def test_un_integrity_error_no_es_busy() -> None:
    error = _dbapi("23505", IntegrityError)
    assert translate_busy(error) is None


def test_sin_sqlstate_ni_dbapi_no_hay_traduccion() -> None:
    sin_orig = DBAPIError("SELECT 1", {}, Exception("sin sqlstate"))
    assert sqlstate_of(sin_orig) is None and translate_busy(sin_orig) is None
    assert sqlstate_of(ValueError("x")) is None and translate_busy(ValueError("x")) is None


async def test_un_for_update_bloqueado_da_55p03_y_se_traduce(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    duena, otra = dos_sesiones
    plan = await make_plan(duena, name="Candado W0-2")
    try:
        await duena.execute(
            text("SELECT id FROM plans.plans WHERE id = :id FOR UPDATE"), {"id": plan.id}
        )
        await otra.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError) as excinfo:
            await otra.execute(
                text("SELECT id FROM plans.plans WHERE id = :id FOR UPDATE"), {"id": plan.id}
            )
        assert sqlstate_of(excinfo.value) == LOCK_NOT_AVAILABLE
        busy = translate_busy(excinfo.value)
        assert isinstance(busy, DatabaseBusy) and busy.headers["Retry-After"] == "1"
    finally:
        await otra.rollback()
        await duena.rollback()


async def test_un_statement_timeout_da_57014(engine: AsyncEngine) -> None:
    async with engine.connect() as conexion:
        await conexion.begin()
        await conexion.execute(text("SET LOCAL statement_timeout = '100ms'"))
        with pytest.raises(DBAPIError) as excinfo:
            await conexion.execute(text("SELECT pg_sleep(1)"))
        await conexion.rollback()
    assert sqlstate_of(excinfo.value) == QUERY_CANCELED
    assert isinstance(translate_busy(excinfo.value), DatabaseBusy)


# get_session (E7) ----------------------------------------------------------------------------


async def _bloquear(duena: AsyncSession, plan_id: UUID) -> None:
    await duena.execute(
        text("SELECT id FROM plans.plans WHERE id = :id FOR UPDATE"), {"id": plan_id}
    )


async def test_get_session_traduce_un_55p03_del_cuerpo(
    dos_sesiones: tuple[AsyncSession, AsyncSession], sesiones_de_get_session: None
) -> None:
    duena, _ = dos_sesiones
    plan = await make_plan(duena, name="Candado cuerpo")
    generador = get_session()
    try:
        await _bloquear(duena, plan.id)
        sesion = await generador.__anext__()
        await sesion.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError) as original:
            await sesion.execute(
                text("SELECT id FROM plans.plans WHERE id = :id FOR UPDATE"), {"id": plan.id}
            )
        # FastAPI lanza dentro de la dependencia la excepción de la ruta.
        with pytest.raises(DatabaseBusy) as excinfo:
            await generador.athrow(original.value)
        assert excinfo.value.__cause__ is original.value
        assert excinfo.value.headers["Retry-After"] == "1"
    finally:
        await generador.aclose()
        await duena.rollback()


async def test_get_session_traduce_un_55p03_al_confirmar(
    dos_sesiones: tuple[AsyncSession, AsyncSession], sesiones_de_get_session: None
) -> None:
    """E7: el `UPDATE` pendiente sale en el flush del commit (`__aexit__` de `session.begin()`)
    y espera el candado de la otra sesión hasta el `lock_timeout` de 200 ms."""
    duena, _ = dos_sesiones
    plan = await make_plan(duena, name="Candado commit")
    generador = get_session()
    try:
        await _bloquear(duena, plan.id)
        with actor_scope(SYSTEM_USER_ID):
            sesion = await generador.__anext__()
            await sesion.execute(text("SET LOCAL lock_timeout = '200ms'"))
            fila = await sesion.get(Plan, plan.id)
            assert fila is not None
            fila.name = "Candado commit (cambiado)"  # sin flush: lo hace el commit
            with pytest.raises(DatabaseBusy) as excinfo:
                await generador.__anext__()
        causa: Any = excinfo.value.__cause__
        assert isinstance(causa, DBAPIError) and sqlstate_of(causa) == LOCK_NOT_AVAILABLE
    finally:
        await generador.aclose()
        await duena.rollback()


async def test_get_session_deja_un_warning_con_solo_el_sqlstate(
    sesiones_de_get_session: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Revisión de seguridad de W0-2 (LOW-1): un 503 `busy` deja rastro operativo en el log
    (`db busy` con el SQLSTATE), sin la sentencia ni traza de nivel `ERROR`."""
    generador = get_session()
    await generador.__anext__()
    with caplog.at_level(logging.INFO, logger="app.db"), pytest.raises(DatabaseBusy):
        await generador.athrow(_dbapi(LOCK_NOT_AVAILABLE))
    registros = [r for r in caplog.records if r.name == "app.db"]
    assert [(r.levelno, r.getMessage()) for r in registros] == [(logging.WARNING, "db busy")]
    assert getattr(registros[0], "sqlstate", None) == LOCK_NOT_AVAILABLE
    assert registros[0].exc_info is None
    assert "SELECT 1" not in caplog.text


async def test_get_session_no_traduce_otros_errores_de_la_base(
    sesiones_de_get_session: None,
) -> None:
    generador = get_session()
    await generador.__anext__()
    duplicado = _dbapi("23505", IntegrityError)
    with pytest.raises(IntegrityError) as excinfo:
        await generador.athrow(duplicado)
    assert excinfo.value is duplicado


async def test_get_session_deja_pasar_los_errores_de_dominio(
    sesiones_de_get_session: None,
) -> None:
    generador = get_session()
    await generador.__anext__()
    with pytest.raises(DomainError, match="otra cosa"):
        await generador.athrow(DomainError("conflict", "otra cosa"))


# migrations/env.py (E7) ----------------------------------------------------------------------


def _llamadas(arbol: ast.AST) -> set[str]:
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, ast.ImportFrom):
            nombres.update(alias.name for alias in nodo.names)
    return nombres


def test_las_migraciones_no_usan_create_engine_from() -> None:
    """E7: `run_async_migrations` arma su propio engine sin `server_settings`; las migraciones no
    heredan los tiempos de espera (RUNBOOK §9)."""
    arbol = ast.parse(ENV_PY.read_text(encoding="utf-8"), filename=str(ENV_PY))
    funciones = {n.name for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef)}
    assert "run_async_migrations" in funciones
    nombres = _llamadas(arbol)
    assert "create_engine_from" not in nombres
    assert "server_settings_from" not in nombres and "server_settings" not in nombres
