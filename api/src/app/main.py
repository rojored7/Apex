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
from fastapi.middleware.cors import CORSMiddleware

from app.core import db, health
from app.core.audit import install_audit_listeners
from app.core.config import Settings, check_secrets_or_exit, get_settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.oplog import install_oplog_listeners
from app.core.crypto.provider import configure_provider, current_provider, get_key_provider
from app.core.crypto.types import install_crypto_type_listeners
from app.core.errors import register_error_handlers
from app.core.logging import RequestLogMiddleware, configure_logging
from app.core.ratelimit import KEY_KINDS, configure_store_limits, rate_limits_from
from app.core.security import configure_security, get_principal_loader

# Módulos de v0.1 en orden de carga; cada historia de módulo agrega el suyo.
MODULES: Final[tuple[str, ...]] = ("auth", "settings", "audit", "members", "plans")
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
    """Un router plano por módulo. El keyring ya no se refresca aquí: lo hace `current_user`
    tras validar el token (`keyring.refresh_current`, S2-D11), así las rutas públicas y un
    token inválido no abren `crypto_keys`."""
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


async def _startup(
    settings: Settings, *, run_migrations_on_startup: bool, migrations_script_location: str | None
) -> None:
    """Arranque del lifespan (revisión Python M7: sale de `create_app`). Migraciones, secretos,
    seguridad y proveedor de llaves, el cargador del principal, el keyring y los pasos
    registrados. Cualquier fallo se registra (sin material) y se relanza: el api no acepta
    tráfico."""
    if run_migrations_on_startup:
        try:
            await asyncio.to_thread(run_migrations, settings, migrations_script_location)
        except Exception:
            logger.exception("las migraciones fallaron al arrancar; el api no acepta tráfico")
            raise
        logger.info("migraciones al día")
    # US-023/US-033: proveedor de llaves y llaves JWT se abren antes que cualquier paso; sin KEK
    # (o con permisos abiertos) o sin llave JWT el proceso termina y el log nunca lleva material.
    try:
        check_secrets_or_exit(settings)  # US-039: nombres de variable, nunca valores
        configure_security(settings)
        configure_provider(get_key_provider(settings))
    except Exception:
        logger.exception("el proveedor de llaves no está disponible; el api no acepta tráfico")
        raise
    logger.info("proveedor de llaves listo: %s", settings.CRYPTO_PROVIDER)
    # US-034: cerrado por defecto; sin cargador de principal nadie puede autenticar.
    try:
        get_principal_loader()
    except RuntimeError:
        logger.error("no hay PrincipalLoader registrado (módulo auth); el api no arranca")
        raise
    with actor_scope(SYSTEM_USER_ID):
        # US-025/US-026: crea las DEK y llaves de índice que falten y carga el keyring.
        async with db.get_sessionmaker()() as session, session.begin():
            keyring = await ensure_keys(session, current_provider())
        logger.info("llaves del bus cargadas: %s", keyring)
        for nombre, paso in list(_startup_steps):
            logger.info("arranque: %s", nombre)
            await paso(settings)


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    """Envelope de errores, log de acceso, límites (US-036) y CORS cerrado (US-037)."""
    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    # US-036: redes de confianza y tope del limitador, leídos por rate_limit().
    app.state.trusted_proxies = settings.trusted_proxies
    app.state.rate_limits = rate_limits_from(settings)  # topes por IP de las rutas (E5)
    configure_store_limits(dict.fromkeys(KEY_KINDS, settings.RATE_LIMIT_MAX_KEYS))  # L-11
    # US-037: CORS cerrado; solo si hay orígenes, exactos y sin credenciales.
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
            max_age=600,
        )
        logger.info("CORS habilitado para: %s", ", ".join(settings.CORS_ORIGINS))


def create_app(
    settings: Settings | None = None,
    *,
    run_migrations_on_startup: bool = True,
    migrations_script_location: str | None = None,
) -> FastAPI:
    """La app del api: logs, engine, listeners del bus y la auditoría, middleware, services de
    los módulos y routers bajo `/api/v1` (y `/health` también en la raíz)."""
    settings = settings or get_settings()
    configure_logging(settings)
    db.configure_engine(db.create_engine_from(settings))
    install_audit_listeners()  # US-016: created_by y auditoría en cada flush
    install_oplog_listeners()  # US-029: crypto_ops en el commit de cada unidad de trabajo
    install_crypto_type_listeners()  # US-028: cifra los Secret pendientes en cada flush

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            await _startup(
                settings,
                run_migrations_on_startup=run_migrations_on_startup,
                migrations_script_location=migrations_script_location,
            )
            yield
        finally:
            configure_keyring(None)
            configure_provider(None)
            await db.dispose_engine()

    produccion = settings.is_production
    app = FastAPI(
        title="APEX API",
        version=settings.APP_VERSION,
        lifespan=lifespan,  # los errores los declara cada ruta con `responses_for` (M7)
        docs_url=None if produccion else "/docs",
        redoc_url=None if produccion else "/redoc",
        openapi_url=None if produccion else "/openapi.json",
    )
    app.state.settings = settings
    _install_middleware(app, settings)
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
