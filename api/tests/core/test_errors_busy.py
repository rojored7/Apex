"""503 `busy` en el envelope de errores (S3-W0-2; S3-D67, E7 y E16).

- Una ruta real cuyo service lanza `DatabaseBusy` responde 503 con
  `{"error": {"code": "busy", "message": ...}}`, `Retry-After: 1` y `Cache-Control: no-store`,
  sin traza a nivel `ERROR` (es una espera agotada, no un fallo del api).
- Un `DBAPIError` con otro SQLSTATE sigue siendo 500 `internal_error`.
- E16: con el `get_session` real (sin override) un 55P03 **al confirmar** también da 503 `busy`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, current_actor
from app.core.db import DatabaseBusy, SessionDep, configure_sessionmaker
from app.core.errors import register_error_handlers
from app.modules.plans import service as plans_service
from app.modules.plans.models import Plan
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.plans import make_plan

PLANS = "/api/v1/plans"
MENSAJE_BUSY = "La base de datos está ocupada; intenta de nuevo en un momento."
MENSAJE_500 = "Ocurrió un error inesperado. Intente de nuevo."


class _ErrorDelAdaptador(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"sqlstate {sqlstate}")
        self.sqlstate = sqlstate


@pytest.fixture
async def cliente(api_prueba: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente de la app real que devuelve los 500 como respuesta (no los re-lanza)."""
    transporte = ASGITransport(app=api_prueba, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        yield c


def _errores(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_un_service_que_lanza_database_busy_da_503_busy(
    cliente: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")

    async def ocupada(*args: Any, **kwargs: Any) -> Any:
        raise DatabaseBusy()

    monkeypatch.setattr(plans_service, "list", ocupada)
    with caplog.at_level(logging.INFO):
        r = await cliente.get(PLANS, headers=cabeceras(admin))
    assert r.status_code == 503, r.text
    assert r.json() == {"error": {"code": "busy", "message": MENSAJE_BUSY}}
    assert r.headers["retry-after"] == "1"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-type"].startswith("application/json")
    assert _errores(caplog) == [], "un 503 busy no deja traza de error"


async def test_un_dbapi_error_con_otro_sqlstate_sigue_siendo_500(
    cliente: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")

    async def rota(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("INSERT", {}, _ErrorDelAdaptador("23505"))

    monkeypatch.setattr(plans_service, "list", rota)
    r = await cliente.get(PLANS, headers=cabeceras(admin))
    assert r.status_code == 500, r.text
    assert r.json() == {"error": {"code": "internal_error", "message": MENSAJE_500}}
    assert "retry-after" not in r.headers
    assert "23505" not in r.text and "INSERT" not in r.text


# E16: `get_session` real y 55P03 al confirmar -----------------------------------------------


@pytest.fixture
def get_session_real(engine: AsyncEngine) -> Iterator[None]:
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        configure_sessionmaker(None)


def _app_con_sesion_real() -> FastAPI:
    """App mínima con el envelope de US-017 y una ruta que deja un `UPDATE` pendiente para el
    commit de `get_session` (sin `dependency_overrides`)."""
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/planes/{plan_id}/renombrar")
    async def renombrar(plan_id: UUID, session: SessionDep) -> dict[str, str]:
        current_actor.set(SYSTEM_USER_ID)  # como `current_user`: sin reset (lo lee el flush)
        await session.execute(text("SET LOCAL lock_timeout = '200ms'"))
        plan = await session.get(Plan, plan_id)
        assert plan is not None
        plan.name = "Renombrado al confirmar"  # sin flush: lo hace el commit
        return {"estado": "pendiente"}

    return app


async def test_con_get_session_real_un_55p03_al_confirmar_da_503_busy(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    get_session_real: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    duena, _ = dos_sesiones
    plan_id = (await make_plan(duena, name="Candado HTTP")).id  # el rollback expira el objeto
    transporte = ASGITransport(app=_app_con_sesion_real(), raise_app_exceptions=False)
    try:
        await duena.execute(
            text("SELECT id FROM plans.plans WHERE id = :id FOR UPDATE"), {"id": plan_id}
        )
        async with AsyncClient(transport=transporte, base_url="http://t") as c:
            with caplog.at_level(logging.INFO):
                r = await c.post(f"/planes/{plan_id}/renombrar")
        assert r.status_code == 503, r.text
        assert r.json() == {"error": {"code": "busy", "message": MENSAJE_BUSY}}
        assert r.headers["retry-after"] == "1"
        assert _errores(caplog) == []
    finally:
        await duena.rollback()
    nombre = await duena.scalar(
        text("SELECT name FROM plans.plans WHERE id = :id"), {"id": plan_id}
    )
    await duena.rollback()
    assert nombre == "Candado HTTP", "el UPDATE que no obtuvo el candado no quedó"


async def test_con_get_session_real_sin_espera_el_cambio_se_confirma(
    dos_sesiones: tuple[AsyncSession, AsyncSession], get_session_real: None
) -> None:
    """Control: sin la otra sesión bloqueando, la misma ruta confirma y responde 200."""
    duena, _ = dos_sesiones
    plan_id = (await make_plan(duena, name="Sin candado")).id
    transporte = ASGITransport(app=_app_con_sesion_real(), raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        r = await c.post(f"/planes/{plan_id}/renombrar")
    assert r.status_code == 200, r.text
    nombre = await duena.scalar(
        text("SELECT name FROM plans.plans WHERE id = :id"), {"id": plan_id}
    )
    await duena.rollback()
    assert nombre == "Renombrado al confirmar"


def test_database_busy_no_es_un_dbapi_error() -> None:
    """El 503 sale por `_handler_dominio` (US-017), nunca por el handler de 500."""
    assert not isinstance(DatabaseBusy(), DBAPIError)
