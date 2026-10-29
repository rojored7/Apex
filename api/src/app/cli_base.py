"""Base común de la capa de aplicación del CLI (S4B-D28 a D31, D62; extraída de `cli.py` en B0).

La comparten `cli.py` (que la reexporta) y `cli_ops/`, que no puede importar `cli` (ciclo).
`get_settings` es el único símbolo de configuración de los comandos (S4B-D29). Es el único
archivo de la capa que arranca el cifrado de columnas (S4B-D30) y no importa `models` ajenos.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Final, NoReturn
from uuid import UUID, uuid4

import typer

from app.core.config import Settings
from app.core.config import get_settings as get_settings
from app.core.context import SYSTEM_USER_ID, actor_scope, batch_scope

DB_TIMEOUTS_CHOICES: Final = ("on", "off")


@contextmanager
def unit_of_work(actor_id: UUID | None = None) -> Iterator[UUID]:
    """Actor y lote de un comando (N-15, US-029): el usuario de `--as` o `SYSTEM_USER_ID`."""
    lote = uuid4()
    with actor_scope(actor_id or SYSTEM_USER_ID), batch_scope(lote):
        yield lote


async def resolve_actor(session: Any, email: str | None) -> UUID:
    """`--as <email>` → id de esa persona `active`; sin `--as`, el usuario técnico. Una cuenta
    inactiva, bloqueada, pendiente o técnica no atribuye acciones: sale con 2 (L-4)."""
    if email is None:
        return SYSTEM_USER_ID
    from app.modules.auth.service import active_user_id_by_email, ids_by_email

    quien = await active_user_id_by_email(session, email)
    if quien is not None:
        return quien
    if await ids_by_email(session, [email]):
        typer.echo(
            "--as: esa cuenta no está activa (inactiva, bloqueada, pendiente o técnica)", err=True
        )
    else:
        typer.echo("--as: no existe un usuario con ese correo", err=True)
    raise typer.Exit(code=2)


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    """Opciones globales de UNA invocación (E7): el callback las deja en `ctx.obj` y cada
    comando se las pasa a `cli_runtime` (PL1 del Sprint 3: antes eran un global mutable)."""

    db_timeouts: bool = True


def runtime_options(ctx: typer.Context) -> RuntimeOptions:
    """Las opciones que dejó el callback; las de por defecto si el comando corre sin él."""
    return ctx.obj if isinstance(ctx.obj, RuntimeOptions) else RuntimeOptions()


def _sin_tiempos_de_espera(settings: Settings) -> Settings:
    """Copia de `settings` con los tres `DB_*_TIMEOUT_MS` en 0 (`--db-timeouts off`, E7)."""
    nombres = ("DB_LOCK_TIMEOUT_MS", "DB_STATEMENT_TIMEOUT_MS", "DB_IDLE_IN_TX_TIMEOUT_MS")
    return settings.model_copy(update=dict.fromkeys(nombres, 0))


def _load_module_services() -> None:
    """Importa el `service.py` de cada módulo para que sus suscriptores del bus (la auditoría,
    S2-B6) existan en el proceso. Import perezoso: `export-openapi` no lo necesita."""
    from app import main

    main.load_module_services()


@asynccontextmanager
async def cli_runtime(
    settings: Settings, options: RuntimeOptions | None = None
) -> AsyncIterator[Any]:
    """Preámbulo de los comandos que escriben (M8): listeners de auditoría, `crypto_ops` y
    cifrado, services de los módulos (suscriptores del bus) y engine de `Settings`; cede una
    `AsyncSession` sin transacción y libera el engine al salir. Con `db_timeouts` falso
    (`--db-timeouts off`, E7) el engine usa una copia con los tres tiempos en 0."""
    from app.core import db
    from app.core.audit import install_audit_listeners
    from app.core.crypto.oplog import install_oplog_listeners
    from app.core.crypto.types import install_crypto_type_listeners

    install_audit_listeners()
    install_oplog_listeners()
    install_crypto_type_listeners()
    _load_module_services()
    opciones = options or RuntimeOptions()
    efectivos = settings if opciones.db_timeouts else _sin_tiempos_de_espera(settings)
    db.configure_engine(db.create_engine_from(efectivos))
    try:
        async with db.get_sessionmaker()() as session:
            yield session
    finally:
        await db.dispose_engine()


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, o un hilo con su propio loop si ya hay uno activo (pruebas async), con
    una copia del contexto de quien llama (reloj y actor llegan igual que sin hilo)."""
    import asyncio
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    contexto = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        return ejecutor.submit(contexto.run, asyncio.run, coro).result()


def reject(mensaje: str, comando: str) -> NoReturn:
    typer.echo(f"{comando}: {mensaje}", err=True)
    raise typer.Exit(code=2)


def production_guard_error(
    settings: Settings, opciones: RuntimeOptions, actor: str | None
) -> str | None:
    """S4A-D53: con `ENV=production` se exige `--as` y se rechaza `--db-timeouts off`."""
    if settings.ENV != "production":
        return None
    if actor is None:
        return "--as <correo> es obligatorio con ENV=production"
    if not opciones.db_timeouts:
        return "--db-timeouts off no se acepta con ENV=production"
    return None


async def resolve_admin_actor(session: Any, email: str | None, *, required: bool = True) -> UUID:
    """`--as <email>` → id de un admin `active` (S4B-D31), o salida 2. Sin `--as`: `required`
    lo exige; si no, el usuario técnico."""
    if email is None:
        if required:
            typer.echo("--as es obligatorio", err=True)
            raise typer.Exit(code=2)
        return SYSTEM_USER_ID
    from app.modules.auth.service import active_admin_id_by_email

    quien = await active_admin_id_by_email(session, email)
    if quien is None:
        typer.echo("--as: no existe un admin activo con ese correo", err=True)
        raise typer.Exit(code=2)
    return quien


@asynccontextmanager
async def crypto_runtime(
    settings: Settings, options: RuntimeOptions | None = None, *, persist_keys: bool = True
) -> AsyncIterator[Any]:
    """`cli_runtime` con proveedor y keyring cargados (S4B-D30), para los comandos que cifran
    (no para los de KEK, S4B-D62). Sin KEK sale con 2 y un mensaje sin ruta. `persist_keys=False`
    no escribe llaves nuevas (`--dry-run`)."""
    from app.core.crypto.errors import CryptoError
    from app.core.crypto.provider import configure_provider, get_key_provider

    try:
        configure_provider(get_key_provider(settings))
    except CryptoError:
        typer.echo("proveedor de llaves no disponible: revise CRYPTO_PROVIDER y la KEK", err=True)
        raise typer.Exit(code=2) from None
    from app.cli_keyring import load_keyring

    async with cli_runtime(settings, options) as session:
        await load_keyring(session, persist=persist_keys)
        yield session
