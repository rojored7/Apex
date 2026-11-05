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
import gc
import importlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Final

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import db, health
from app.core.audit import install_audit_listeners
from app.core.backup_status import PUBLIC_BACKUP, backup_health
from app.core.config import Settings, check_secrets_or_exit, get_settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.oplog import install_oplog_listeners
from app.core.crypto.provider import configure_provider, current_provider, get_provider_named
from app.core.crypto.recovery import is_loaded, observe, poll_forever, reset, try_load
from app.core.crypto.state import CryptoState, ThresholdAware, health_state
from app.core.crypto.types import install_crypto_type_listeners
from app.core.errors import register_error_handlers
from app.core.logging import RequestLogMiddleware, configure_logging
from app.core.migrations_status import configure_migrations, migrations_health
from app.core.ratelimit import (
    KEY_KINDS,
    configure_store_limits,
    rate_limits_from,
    user_limits_from,
)
from app.core.security import configure_security, get_principal_loader

# Módulos de v0.1 en orden de carga; cada historia de módulo agrega el suyo.
MODULES: Final[tuple[str, ...]] = (
    "auth",
    "settings",
    "audit",
    "members",
    "plans",
    "memberships",
    "payments",
    "dashboard",  # S4A-B8 (S4A-D27): lectura; nadie lo importa, importa a los demás
)
API_PREFIX = "/api/v1"
MIGRATION_LOCK_KEY: Final[int] = db.MIGRATION_LOCK_KEY
API_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger("app.main")

StartupStep = Callable[[Settings], Awaitable[None]]
_startup_steps: list[tuple[str, StartupStep]] = []
_app: FastAPI | None = None


def register_startup_step(name: str, fn: StartupStep) -> None:
    """Paso que corre al arrancar, después de las migraciones, en orden de registro.

    S5-D199: solo corre con el custodio de llaves en estado `ok`. Si el api arranca sellado los
    pasos quedan pendientes y el sondeo los ejecuta UNA vez, en la primera recuperación."""
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


def _failed_revision(cfg: Config) -> str | None:
    """Revisión que estaba aplicando Alembic cuando falló: la que sigue a la última aplicada (que
    `migrations/env.py` anota en `cfg.attributes`). Solo ids de revisión, nunca la URL."""
    ultima = cfg.attributes.get("ultima_revision")
    try:
        pendientes = list(
            ScriptDirectory.from_config(cfg).iterate_revisions("head", ultima or "base")
        )
    except Exception:  # pragma: no cover - cadena ilegible: se loguea sin revisión
        return None
    return pendientes[-1].revision if pendientes else None


def run_migrations(settings: Settings, script_location: str | None = None) -> None:
    """`alembic upgrade head`. Síncrono: desde el loop se llama con `asyncio.to_thread`. Si falla,
    el error se relanza con `apex_revision` (la revisión que falló) para que el log la nombre."""
    cfg = alembic_config(settings, script_location)
    try:
        command.upgrade(cfg, "head")
    except Exception as error:
        error.apex_revision = _failed_revision(cfg)  # type: ignore[attr-defined]
        raise


async def _run_startup_steps(settings: Settings) -> None:
    """Los pasos registrados, en orden, como el sistema (S5-D199)."""
    with actor_scope(SYSTEM_USER_ID):
        for nombre, paso in list(_startup_steps):
            logger.info("arranque: %s", nombre)
            await paso(settings)


async def _startup(
    settings: Settings, *, run_migrations_on_startup: bool, migrations_script_location: str | None
) -> CryptoState:
    """Arranque del lifespan (revisión Python M7: sale de `create_app`). Migraciones, secretos,
    seguridad y proveedor de llaves, el cargador del principal, el keyring y los pasos
    registrados. Cualquier fallo se registra (sin material) y se relanza: el api no acepta
    tráfico."""
    if run_migrations_on_startup:
        try:
            await asyncio.to_thread(run_migrations, settings, migrations_script_location)
        except Exception as error:
            logger.exception(
                "las migraciones fallaron al arrancar; el api no acepta tráfico",
                extra={"revision": getattr(error, "apex_revision", None)},
            )
            raise
        logger.info("migraciones al día")
    # US-023/US-033: proveedor de llaves y llaves JWT se abren antes que cualquier paso; sin KEK
    # (o con permisos abiertos) o sin llave JWT el proceso termina y el log nunca lleva material.
    try:
        check_secrets_or_exit(settings)  # US-039: nombres de variable, nunca valores
        configure_security(settings)
        configure_provider(get_provider_named(settings, settings.CRYPTO_PROVIDER))
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
        # US-025/US-026: crea las DEK y llaves de índice que falten y carga el keyring. S5-D14
        # (M-4): solo un custodio `sealed` o `unreachable` degrada el arranque (sin keyring, el
        # sondeo del lifespan lo recupera); `unwrap_failed`, `key_missing` y `forbidden` abortan.
        estado = await try_load(db.get_sessionmaker(), settings, create_missing=True)
        if estado == "ok":
            logger.info("llaves del bus cargadas")
        else:
            logger.warning("crypto sealed at startup: el api arranca sin keyring (%s)", estado)
        if estado == "ok":
            await _run_startup_steps(settings)
    # S4B-D48: lo que vive todo el proceso (módulos, rutas, esquemas, llaves) pasa a la generación
    # permanente; el GC de generación 2 deja de escanearlo y las pausas bajo carga se acortan.
    gc.collect()  # S4B-D179: sin esto el freeze congelaría basura cíclica del arranque para siempre
    gc.freeze()
    return estado


async def _cancel_crypto_poll(app: FastAPI) -> None:
    """Cancela el sondeo de recuperación del lifespan y espera su fin (S5-D195)."""
    tarea: asyncio.Task[None] | None = getattr(app.state, "crypto_poll", None)
    app.state.crypto_poll = None
    if tarea is None:
        return
    tarea.cancel()
    await asyncio.gather(tarea, return_exceptions=True)


async def _cancel_background_verifications() -> None:
    """S4A-D44 (H-2): el `shutdown` cancela las verificaciones 202 en curso y espera su `finally`
    (sueltan el candado `4_270_003`) antes de cerrar el engine. Import por nombre, como
    `load_module_services`: `main.py` es el único que conoce los módulos."""
    audit_service = importlib.import_module("app.modules.audit.service")
    await audit_service.cancel_background_verifications()


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    """Envelope de errores, log de acceso, límites (US-036) y CORS cerrado (US-037)."""
    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    # US-036: redes de confianza y tope del limitador, leídos por rate_limit().
    app.state.trusted_proxies = settings.trusted_proxies
    app.state.rate_limits = rate_limits_from(settings)  # topes por IP de las rutas (E5)
    app.state.user_limits = user_limits_from(settings)  # topes por usuario (E10, E15)
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


def _should_migrate(settings: Settings, explicito: bool | None) -> bool:
    """S4B-D8: el argumento explícito de `create_app` manda; con `None`, `MIGRATE_ON_STARTUP`."""
    return settings.MIGRATE_ON_STARTUP if explicito is None else explicito


def _make_lifespan(
    settings: Settings, migrar: bool, migrations_script_location: str | None
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            estado = await _startup(
                settings,
                run_migrations_on_startup=migrar,
                migrations_script_location=migrations_script_location,
            )
            if estado != "ok":
                # S5-D16, S5-D195: arrancó sellado; el sondeo reintenta cada CRYPTO_RECOVERY_POLL_S.
                app.state.crypto_poll = asyncio.create_task(
                    poll_forever(
                        db.get_sessionmaker(),
                        settings,
                        create_missing=True,
                        on_loaded=lambda: _run_startup_steps(settings),
                    ),
                    name="poll_forever",
                )
            yield
        finally:
            await _cancel_crypto_poll(app)
            await _cancel_background_verifications()
            configure_keyring(None)
            configure_provider(None)
            reset()  # S5-D198: la app siguiente del proceso parte sin estado ni aviso previos
            await db.dispose_engine()

    return lifespan


def _crypto_health_check(settings: Settings) -> Callable[[], Awaitable[str]]:
    """Check `crypto` de `/health` (S5-D13, S5-D194, S5-D196). Solo pregunta `status()` al
    proveedor y mira si el proceso tiene keyring: nunca abre llaves (S5-D70). Con `ENV=production`
    y un umbral de desello menor que 2 (un solo custodio puede desellar) responde `unreachable` y
    deja UNA línea CRITICAL por transición, sin URL ni versión (M-3, L-7)."""
    umbral_malo = False

    async def crypto() -> str:
        nonlocal umbral_malo
        proveedor = current_provider()
        estado = await proveedor.status()
        # Sin umbral conocido (proveedor local, o aún sin leer) no se avisa (S5-D196, L6).
        umbral = proveedor.unseal_threshold if isinstance(proveedor, ThresholdAware) else None
        umbral_ok = not (settings.is_production and umbral is not None and umbral < 2)
        if not umbral_ok and not umbral_malo:
            logger.critical("crypto threshold below 2 in production; unseal needs more key holders")
        umbral_malo = not umbral_ok
        publico = health_state(estado, is_loaded(), threshold_ok=umbral_ok)
        observe(publico)  # S5-D202: un re-sellado con las llaves en memoria también avisa
        return publico

    return crypto


def _register_health_checks(settings: Settings, migrations_script_location: str | None) -> None:
    """Comprobaciones extra de `/health`. `backup` es informativo (S4B-D26, S4B-D60): el 200 se
    mantiene sea cual sea su valor. `migrations` es crítico (S4B-D27): solo `ok` mantiene el 200;
    `head` y las revisiones conocidas se leen del código una vez, aquí (las pruebas de /health no
    abren el lifespan)."""
    health.register_health_check(
        "crypto",
        _crypto_health_check(settings),
        critical=True,
        allowed={"ok", "sealed", "unreachable", "unknown"},
        healthy={"ok"},
    )
    health.register_health_check(
        "backup", backup_health, critical=False, allowed=PUBLIC_BACKUP, healthy={"ok"}
    )
    script = ScriptDirectory.from_config(alembic_config(settings, migrations_script_location))
    head = script.get_current_head()
    if head is None:  # pragma: no cover - el repo siempre trae migraciones
        raise RuntimeError("no hay migraciones de Alembic en el código")
    configure_migrations(head, frozenset(r.revision for r in script.walk_revisions()))
    health.register_health_check(
        "migrations",
        migrations_health,
        critical=True,
        allowed={"ok", "mismatch", "unknown"},
        healthy={"ok"},
    )


def create_app(
    settings: Settings | None = None,
    *,
    run_migrations_on_startup: bool | None = None,
    migrations_script_location: str | None = None,
) -> FastAPI:
    """La app del api: logs, engine, listeners del bus y la auditoría, middleware, services de
    los módulos y routers bajo `/api/v1` (y `/health` también en la raíz). Migra al arrancar según
    `run_migrations_on_startup`; con `None` manda `Settings.MIGRATE_ON_STARTUP` (S4B-D8)."""
    settings = settings or get_settings()
    configure_logging(settings)
    db.configure_engine(db.create_engine_from(settings))
    install_audit_listeners()  # US-016: created_by y auditoría en cada flush
    install_oplog_listeners()  # US-029: crypto_ops en el commit de cada unidad de trabajo
    install_crypto_type_listeners()  # US-028: cifra los Secret pendientes en cada flush

    migrar = _should_migrate(settings, run_migrations_on_startup)
    lifespan = _make_lifespan(settings, migrar, migrations_script_location)
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
    _register_health_checks(settings, migrations_script_location)

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
