"""Punto de entrada del api: `create_app()` (US-020).

`create_app()` valida la configuración, configura los logs, registra el envelope de
errores, el middleware de acceso, carga los services de los módulos (suscripciones
del bus, US-014), monta los routers bajo `/api/v1` y el de salud también en `/`.
El `lifespan` corre `alembic upgrade head` en un hilo aparte (el `asyncio.run` de
`env.py` no choca con el loop de Uvicorn) bajo el lock asesor de `migrations/env.py`,
y luego los pasos de `register_startup_step` (US-025 abre las DEKs). Si una
migración falla, el error se relanza y el api no acepta tráfico.

Para Uvicorn, `app.main:app` se construye perezosamente (PEP 562): importar
`create_app` no arranca nada, así US-021 exporta el OpenAPI sin `.env`.

`main.py` es el único lugar que conoce la lista `MODULES`; `core/` no importa
módulos. `install_audit_listeners()` (US-016) se instala en `create_app`; los pasos de
arranque corren bajo `actor_scope(SYSTEM_USER_ID)` porque pueden escribir tablas con
`created_by` (por ejemplo `ensure_keys`, US-025).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

from alembic import command
from alembic.config import Config
from fastapi import APIRouter, FastAPI

from app.core import db, health
from app.core.audit import install_audit_listeners
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.config import Settings, get_settings
from app.core.errors import ERROR_RESPONSES, register_error_handlers
from app.core.logging import RequestLogMiddleware, configure_logging

# Módulos de v0.1 en orden de carga; cada historia de módulo agrega el suyo.
MODULES: Final[tuple[str, ...]] = ()
API_PREFIX = "/api/v1"
MIGRATION_LOCK_KEY: Final[int] = db.MIGRATION_LOCK_KEY
API_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger("app.main")

StartupStep = Callable[[Settings], Awaitable[None]]
_startup_steps: list[tuple[str, StartupStep]] = []
_app: FastAPI | None = None


def register_startup_step(name: str, fn: StartupStep) -> None:
    """Paso que corre al arrancar, después de las migraciones, en orden de registro."""
    _startup_steps.append((name, fn))


def clear_startup_steps() -> None:
    """Solo para pruebas."""
    _startup_steps.clear()


def load_module_services() -> None:
    """Importa el `service.py` de cada módulo: ahí se suscriben los handlers del bus."""
    for modulo in MODULES:
        importlib.import_module(f"app.modules.{modulo}.service")


def include_module_routers(router: APIRouter) -> None:
    for modulo in MODULES:
        mod = importlib.import_module(f"app.modules.{modulo}.router")
        router.include_router(mod.router)


def alembic_config(settings: Settings, script_location: str | None = None) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", script_location or str(API_ROOT / "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url", settings.DATABASE_URL.get_secret_value().replace("%", "%%")
    )
    return cfg


def run_migrations(settings: Settings, script_location: str | None = None) -> None:
    """`alembic upgrade head`. Síncrono: desde el loop se llama con `asyncio.to_thread`."""
    command.upgrade(alembic_config(settings, script_location), "head")


def create_app(
    settings: Settings | None = None,
    *,
    run_migrations_on_startup: bool = True,
    migrations_script_location: str | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    db.configure_engine(db.create_engine_from(settings))
    install_audit_listeners()  # US-016: created_by y auditoría en cada flush

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if run_migrations_on_startup:
            try:
                await asyncio.to_thread(run_migrations, settings, migrations_script_location)
            except Exception:
                logger.exception("las migraciones fallaron al arrancar; el api no acepta tráfico")
                raise
            logger.info("migraciones al día")
        with actor_scope(SYSTEM_USER_ID):
            for nombre, paso in list(_startup_steps):
                logger.info("arranque: %s", nombre)
                await paso(settings)
        try:
            yield
        finally:
            await db.dispose_engine()

    produccion = settings.is_production
    app = FastAPI(
        title="APEX API",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
        docs_url=None if produccion else "/docs",
        redoc_url=None if produccion else "/redoc",
        openapi_url=None if produccion else "/openapi.json",
    )
    app.state.settings = settings
    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    load_module_services()

    api = APIRouter(prefix=API_PREFIX)
    include_module_routers(api)
    api.include_router(health.router)
    app.include_router(api)
    app.include_router(health.router)
    return app


def __getattr__(name: str) -> Any:
    """`app.main:app` para Uvicorn, construida la primera vez que se pide."""
    if name == "app":
        global _app
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
