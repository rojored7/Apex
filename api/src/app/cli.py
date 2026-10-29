"""Comandos del api (`python -m app.cli`; en Compose, `docker compose run --rm tools <cmd>`).

- `export-openapi <ruta>` (US-021): construye `create_app()` con una configuración de
  exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON
  con claves ordenadas, sangría de 2 y salto de línea final. `info.version` es la versión
  del paquete, no `APP_VERSION`, para que la salida no cambie con cada commit. No escribe
  en tablas, así que no necesita actor.

Comandos siguientes: `init-keys` (US-023), `seed --as` (US-041), `issue-reset-link --as`
(S2-B4, L-13), `unlock-user --as` (S2-B5; `--as` obligatorio desde la revisión V10, N-4),
`import-members`, `rotate-key`, `sign-audit`. Todo comando que escriba tablas acepta
`--as <email>` (N-15) y abre la base con `cli_runtime(settings, runtime_options(ctx))`
(revisión Python M8; las opciones globales van en `ctx.obj`, PL1 de Fase 4 del Sprint 3): instala
los listeners de auditoría, bitácora del bus y cifrado, carga los services de los módulos
(`_load_module_services`, S2-B6) para que los eventos que emite queden auditados, y libera el
engine al terminar.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, Final, NoReturn
from uuid import UUID, uuid4

import typer
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.context import SYSTEM_USER_ID, actor_scope, batch_scope

PACKAGE_NAME = "apex-api"


@contextmanager
def unit_of_work(actor_id: UUID | None = None) -> Iterator[UUID]:
    """Actor y lote de un comando (N-15, US-029): el usuario de `--as` o `SYSTEM_USER_ID`."""
    lote = uuid4()
    with actor_scope(actor_id or SYSTEM_USER_ID), batch_scope(lote):
        yield lote


async def resolve_actor(session: Any, email: str | None) -> UUID:
    """`--as <email>` → id de esa persona en estado `active`; sin `--as`, el usuario técnico.

    L-4 del Sprint 1: una cuenta inactiva, bloqueada, pendiente o el propio
    `system@apex.local` no sirven para atribuir una acción; sale con 2 y lo dice.
    """
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


app = typer.Typer(no_args_is_help=True, add_completion=False)


DB_TIMEOUTS_CHOICES: Final = ("on", "off")


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    """Opciones globales de UNA invocación del CLI (E7): el callback las deja en `ctx.obj` y cada
    comando que abre la base se las pasa a `cli_runtime` (PL1 de la revisión de Fase 4 del
    Sprint 3: antes vivían en un global mutable del proceso)."""

    db_timeouts: bool = True


def runtime_options(ctx: typer.Context) -> RuntimeOptions:
    """Las opciones que dejó el callback; las de por defecto si el comando corre sin él."""
    return ctx.obj if isinstance(ctx.obj, RuntimeOptions) else RuntimeOptions()


@app.callback()
def main(
    ctx: typer.Context,
    db_timeouts: Annotated[
        str,
        typer.Option(
            "--db-timeouts",
            help="off pone en 0 los tres DB_*_TIMEOUT_MS (rotate-key, sign-audit, importación).",
        ),
    ] = "on",
) -> None:
    """Comandos de APEX. `--db-timeouts off` va antes del comando (S3-D43, E7)."""
    if db_timeouts not in DB_TIMEOUTS_CHOICES:
        raise typer.BadParameter(
            f"use {' u '.join(DB_TIMEOUTS_CHOICES)}", param_hint="--db-timeouts"
        )
    # Por invocación (`ctx.obj`): un `off` anterior nunca se arrastra.
    ctx.obj = RuntimeOptions(db_timeouts=db_timeouts == "on")


def _sin_tiempos_de_espera(settings: Settings) -> Settings:
    """Copia de `settings` con los tres `DB_*_TIMEOUT_MS` en 0 (`--db-timeouts off`, E7)."""
    return settings.model_copy(
        update={
            "DB_LOCK_TIMEOUT_MS": 0,
            "DB_STATEMENT_TIMEOUT_MS": 0,
            "DB_IDLE_IN_TX_TIMEOUT_MS": 0,
        }
    )


def export_settings() -> Settings:
    """`Settings` sin validar, con marcadores que no son secretos y no llegan al documento."""
    return Settings.model_construct(
        DATABASE_URL=SecretStr("postgresql+asyncpg://export-no-secret@localhost/export"),
        JWT_PRIVATE_KEY_PATH=Path("export-no-secret.pem"),
        JWT_PUBLIC_KEY_PATH=None,
        CRYPTO_PROVIDER="local",
        CRYPTO_LOCAL_KEK_PATH=Path("export-no-secret.bin"),
        CRYPTO_LOCAL_SIGNING_KEY_PATH=Path("export-no-secret.key"),
        ENV="dev",
        TZ_DISPLAY="America/Bogota",
        UPLOADS_DIR=Path("export-uploads"),
        CORS_ORIGINS=[],
        LOG_LEVEL="WARNING",
        TRUSTED_PROXIES="",
        COOKIE_SECURE=False,
        FRONT_BASE_URL="http://localhost",
        APP_VERSION="export",
    )


def _package_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:  # pragma: no cover - solo sin instalar el paquete
        return "0.0.0"


def build_openapi_document() -> dict[str, Any]:
    """El contrato, desde el código: no entra al `lifespan` ni abre conexiones."""
    from app.main import create_app  # import perezoso: el CLI arranca rápido sin la app

    aplicacion = create_app(export_settings(), run_migrations_on_startup=False)
    doc = aplicacion.openapi()
    doc["info"]["version"] = _package_version()
    return doc


def write_openapi(doc: dict[str, Any], output: Path) -> None:
    """JSON determinista: claves ordenadas, sangría de 2, UTF-8 y fin de línea `\\n`."""
    texto = json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)


@app.command("export-openapi")
def export_openapi(output: Path) -> None:
    """Exporta el contrato OpenAPI a `output`, sin `.env`, base ni llaves."""
    write_openapi(build_openapi_document(), output)
    typer.echo(f"openapi: escrito {output}")


@dataclass(frozen=True)
class KeyPaths:
    kek: Path
    signing_key: Path
    jwt_private: Path
    jwt_public: Path


KEK_LEN = 32
SEED_LEN = 32


def key_paths_in(directory: Path) -> KeyPaths:
    """Rutas estándar dentro de un directorio (el volumen `keys` en Compose)."""
    return KeyPaths(
        kek=directory / "kek.bin",
        signing_key=directory / "sign-ed25519.key",
        jwt_private=directory / "jwt_ed25519.pem",
        jwt_public=directory / "jwt_ed25519.pub",
    )


def key_paths_from_settings(settings: Settings) -> KeyPaths:
    if settings.CRYPTO_LOCAL_KEK_PATH is None:
        raise typer.BadParameter("CRYPTO_LOCAL_KEK_PATH no está definida")
    publica = settings.JWT_PUBLIC_KEY_PATH or settings.JWT_PRIVATE_KEY_PATH.with_suffix(".pub")
    return KeyPaths(
        kek=settings.CRYPTO_LOCAL_KEK_PATH,
        signing_key=settings.CRYPTO_LOCAL_SIGNING_KEY_PATH,
        jwt_private=settings.JWT_PRIVATE_KEY_PATH,
        jwt_public=publica,
    )


def _write_new_private_file(path: Path, data: bytes) -> bool:
    """Crea el archivo con modo 600 solo si no existe (`O_EXCL`). Devuelve si lo creó."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as archivo:
        archivo.write(data)
    return True


def _jwt_pem_pair() -> tuple[bytes, bytes]:
    from app.core.security import generate_jwt_keypair_pem  # solo core/security toca JWT

    return generate_jwt_keypair_pem()


def init_keys_files(paths: KeyPaths) -> dict[str, str]:
    """Crea lo que falte; nunca sobrescribe. Devuelve `{nombre: "creada" | "ya existe"}`."""
    estado: dict[str, str] = {}
    estado["KEK"] = (
        "creada" if _write_new_private_file(paths.kek, os.urandom(KEK_LEN)) else "ya existe"
    )
    estado["llave de firma"] = (
        "creada"
        if _write_new_private_file(paths.signing_key, os.urandom(SEED_LEN))
        else "ya existe"
    )
    if paths.jwt_private.exists() and paths.jwt_public.exists():
        estado["par JWT"] = "ya existe"
    elif paths.jwt_private.exists():
        from app.core.security import public_pem_from_private_pem

        publica = public_pem_from_private_pem(paths.jwt_private.read_bytes())
        _write_new_private_file(paths.jwt_public, publica)
        estado["par JWT"] = "creada (solo la pública, desde la privada existente)"
    else:
        privada, publica = _jwt_pem_pair()
        if paths.jwt_public.exists():
            paths.jwt_public.unlink()  # pública huérfana: se regenera con la privada nueva
        _write_new_private_file(paths.jwt_private, privada)
        _write_new_private_file(paths.jwt_public, publica)
        estado["par JWT"] = "creada"
    return estado


@app.command("init-keys")
def init_keys(
    directory: Annotated[Path | None, typer.Option("--dir")] = None,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    data_class: Annotated[str | None, typer.Option("--data-class")] = None,
) -> None:
    """Crea la KEK, la llave de firma del bus y el par JWT Ed25519 (modo 600), sin sobrescribir.

    Idempotente (A-1): lo que ya existe se conserva. No crea las DEK: las crea el api al
    arrancar (`ensure_keys`, US-025). `--as` solo se anota en el log porque no escribe en
    la base. `--data-class` queda reservado para US-140.
    """
    if data_class is not None:
        typer.echo("init-keys --data-class no implementado todavía (US-140)", err=True)
        raise typer.Exit(code=2)
    rutas = (
        key_paths_in(directory)
        if directory is not None
        else key_paths_from_settings(get_settings())
    )
    estado = init_keys_files(rutas)
    quien = f" (por {actor})" if actor else ""
    for nombre, resultado in estado.items():
        typer.echo(f"init-keys: {nombre}: {resultado}{quien}")


def _load_module_services() -> None:
    """Importa el `service.py` de cada módulo para que los suscriptores del bus (la auditoría
    de `audit`, S2-B6) existan en el proceso del CLI. Import perezoso de `app.main`: el CLI
    arranca rápido y `export-openapi` no lo necesita."""
    from app import main

    main.load_module_services()


@asynccontextmanager
async def cli_runtime(
    settings: Settings, options: RuntimeOptions | None = None
) -> AsyncIterator[Any]:
    """Preámbulo común de los comandos que escriben (revisión Python M8): listeners de
    auditoría (US-016), de `crypto_ops` (US-029) y de cifrado (US-028), los services de los
    módulos (sus suscriptores del bus) y el engine de `Settings`; cede una `AsyncSession` sin
    transacción abierta y libera el engine al salir, falle o no el comando. Con
    `options.db_timeouts` falso (`--db-timeouts off`) el engine sale de una copia con los tres
    tiempos en 0 (E7); sin `options`, los de `Settings`. El `Settings` recibido no se muta."""
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


async def _seed(
    settings: Settings,
    admin_email: str,
    admin_password: str,
    actor_email: str | None,
    *,
    force_change: bool,
    options: RuntimeOptions | None = None,
) -> str:
    from app.core.security import configure_password_hasher, configure_password_policy
    from app.modules.auth.service import seed_admin

    configure_password_hasher(
        settings.ARGON2_TIME_COST, settings.ARGON2_MEMORY_COST_KIB, settings.ARGON2_PARALLELISM
    )
    configure_password_policy(settings.PASSWORD_MIN_LENGTH)
    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            async with session.begin():
                resultado = await seed_admin(
                    session, admin_email, admin_password, by=actor, force_change=force_change
                )
    return resultado.outcome


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, o un hilo con su propio loop si ya hay uno activo (pruebas async). El hilo
    corre con una copia del contexto de quien llama: el reloj (`set_clock`) y el actor llegan al
    comando igual que sin hilo."""
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


@app.command("seed")
def seed(
    ctx: typer.Context,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    no_force_change: Annotated[bool, typer.Option("--no-force-change")] = False,
) -> None:
    """Crea el primer admin activo con ADMIN_EMAIL y ADMIN_INITIAL_PASSWORD (idempotente).

    Las dos variables salen de `.env.seed` o del entorno del servicio tools (`SeedSettings`,
    M-8), nunca de `Settings`. El admin sembrado debe cambiar la contraseña al entrar; solo con
    `ENV=dev` se acepta `--no-force-change`. Sale con 2 si falta el correo, falta la
    contraseña o es débil (L-9: el literal histórico del ejemplo está en la lista de comunes);
    nunca imprime la contraseña.
    """

    from app.core.config import load_seed_settings
    from app.core.security import WeakPasswordError, validate_password_policy
    from app.modules.auth.exceptions import AuthError

    settings = get_settings()
    if no_force_change and settings.ENV != "dev":
        typer.echo("seed: --no-force-change solo se acepta con ENV=dev", err=True)
        raise typer.Exit(code=2)
    semilla = load_seed_settings()
    if not semilla.ADMIN_EMAIL or semilla.ADMIN_INITIAL_PASSWORD is None:
        typer.echo("seed: faltan ADMIN_EMAIL o ADMIN_INITIAL_PASSWORD en .env.seed", err=True)
        raise typer.Exit(code=2)
    clave = semilla.ADMIN_INITIAL_PASSWORD.get_secret_value()
    try:
        validate_password_policy(clave)
    except WeakPasswordError as error:
        typer.echo(f"seed: ADMIN_INITIAL_PASSWORD no cumple la política ({error.reason})", err=True)
        raise typer.Exit(code=2) from None
    try:
        resultado = _run(
            _seed(
                settings,
                semilla.ADMIN_EMAIL,
                clave,
                actor,
                force_change=not no_force_change,
                options=runtime_options(ctx),
            )
        )
    except AuthError as error:
        typer.echo(f"seed: {error.code}", err=True)
        raise typer.Exit(code=2) from None
    if resultado == "created":
        typer.echo("seed: admin inicial creado")
    else:
        typer.echo("seed: omitido: ya existe un admin activo")


@app.command("issue-reset-link")
def issue_reset_link(
    ctx: typer.Context,
    email: str,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Emite el enlace de activación o restablecimiento de `email` y lo imprime una sola vez
    (S2-B4, L-13): la salida para recuperar a un admin, incluida la propia cuenta de quien lo
    invoca, que `POST /users/{id}/resend-link` rechaza. `--as` es obligatorio y debe ser un
    admin activo; deja el `insert` auditado con su `created_by`. Sale con 2 si falta `--as`, si
    no es un admin activo o si la cuenta no puede recibir el enlace (sin revelar si existe).
    """
    if actor is None:
        typer.echo("issue-reset-link: --as <correo de un admin activo> es obligatorio", err=True)
        raise typer.Exit(code=2)
    settings = get_settings()
    salida = _run(_issue_reset_link(settings, email, actor, runtime_options(ctx)))
    if salida is None:
        typer.echo(_LINK_REJECTED, err=True)
        raise typer.Exit(code=2)
    url, purpose, expires_at = salida
    typer.echo(f"issue-reset-link: enlace de {purpose} válido hasta {expires_at}")
    typer.echo(url)


# El mismo texto para un correo inexistente, borrado o no elegible: no revela si existe.
_LINK_REJECTED = "issue-reset-link: esa cuenta no puede recibir un enlace"


async def _issue_reset_link(
    settings: Settings, email: str, actor_email: str, options: RuntimeOptions | None = None
) -> tuple[str, str, str] | None:
    """`(url, propósito, vence)` o `None` si la cuenta no existe o no es elegible. Sale con 2
    (por `resolve_actor` o aquí) si `--as` no es un admin activo."""
    from app.modules.auth.exceptions import UserNotEligible, UserNotFound
    from app.modules.auth.service import issue_link

    async with cli_runtime(settings, options) as session:
        actor, objetivo = await _admin_actor_and_target(session, actor_email, email)
        if objetivo is None:
            return None
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            try:
                async with session.begin():
                    salida = await issue_link(
                        session, objetivo, by=actor, front_base_url=settings.FRONT_BASE_URL
                    )
            except (UserNotFound, UserNotEligible):
                return None
    return salida.url, salida.purpose, salida.expires_at.isoformat()


async def _admin_actor_and_target(
    session: Any, actor_email: str, email: str
) -> tuple[UUID, UUID | None]:
    """`(actor, objetivo)` en una transacción de lectura: `--as` debe ser un admin activo (sale
    con 2 si no) y el objetivo es el id vivo de `email` o `None` (sin revelar si existe)."""
    from app.modules.auth.service import (
        active_admin_id_by_email,
        ids_by_email,
        normalize_login_email,
    )

    async with session.begin():
        actor = await resolve_actor(session, actor_email)
        if await active_admin_id_by_email(session, actor_email) != actor:
            typer.echo("--as: debe ser un admin activo", err=True)
            raise typer.Exit(code=2)
        objetivo = (await ids_by_email(session, [email])).get(normalize_login_email(email))
    return actor, objetivo


@app.command("unlock-user")
def unlock_user(
    ctx: typer.Context,
    email: str,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Desbloquea la cuenta de `email` (S2-B5, US-050; S2-D10): limpia `locked_at` y
    `failed_login_count` con `service.unlock` y deja el `update` auditado con el actor de `--as`,
    obligatorio y admin activo como en `issue-reset-link` (revisión de seguridad V10, N-4: sin él
    el desbloqueo quedaba atribuido al usuario técnico). Corre en otro proceso que el api: los
    contadores en memoria del api se limpian con `up -d api` (docs/RUNBOOK.md). Sale con 2 si
    falta `--as` o no es un admin activo, y con el mismo mensaje y sin repetir el correo si la
    cuenta no existe, está borrada o no está bloqueada.
    """
    if actor is None:
        typer.echo("unlock-user: --as <correo de un admin activo> es obligatorio", err=True)
        raise typer.Exit(code=2)
    settings = get_settings()
    if not _run(_unlock_user(settings, email, actor, runtime_options(ctx))):
        typer.echo(_UNLOCK_REJECTED, err=True)
        raise typer.Exit(code=2)
    typer.echo("unlock-user: cuenta desbloqueada")


# El mismo texto para una cuenta no bloqueada, inexistente o borrada: no revela si existe.
_UNLOCK_REJECTED = "unlock-user: no hay una cuenta bloqueada con ese correo"


async def _unlock_user(
    settings: Settings, email: str, actor_email: str, options: RuntimeOptions | None = None
) -> bool:
    """`True` si desbloqueó; `False` si la cuenta no existe, está borrada o no está bloqueada.
    Sale con 2 (por `resolve_actor` o aquí) si `--as` no es un admin activo."""
    from app.modules.auth.exceptions import NotLocked, UserNotFound
    from app.modules.auth.service import unlock

    async with cli_runtime(settings, options) as session:
        actor, objetivo = await _admin_actor_and_target(session, actor_email, email)
        if objetivo is None:
            return False
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            try:
                async with session.begin():
                    await unlock(session, objetivo, by=actor)
            except (UserNotFound, NotLocked):
                return False
    return True


@app.command("recompute-memberships")
def recompute_memberships(
    ctx: typer.Context,
    on_date: Annotated[str | None, typer.Option("--date")] = None,
    simulate: Annotated[bool, typer.Option("--simulate")] = False,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Recalcula la columna `status` de las membresías (S4A-B2, US-094; S4A-D15, S4A-D48,
    S4A-D53, E5): `memberships.service.recompute_statuses` con `db.get_sessionmaker()` como
    fábrica, bajo `unit_of_work(actor)` (`--as`, o `SYSTEM_USER_ID` sin él).

    - `--date AAAA-MM-DD` distinto de hoy exige `--simulate`, `ENV=dev` y una base de
      `DATABASE_URL` que termine en `_sim` o sea `apex_test` (guarda dura de E5); con
      `--simulate` el reloj es `FrozenClock` a las 12:00 de Bogotá de esa fecha, la primera línea
      de la salida es `RELOJ SIMULADO: <fecha>` y la corrida reclama `expirations_sim`;
    - con `ENV=production` exige `--as` y rechaza `--db-timeouts off` (S4A-D53);
    - imprime solo los conteos de `RecomputeSummary` (nunca ids ni nombres);
    - sale 0, o 1 si `busy_omitidos + errores > 0`, o 2 por argumento inválido, `--as` inválido o
      una guarda incumplida; con `--simulate`, 3 si otra corrida `expirations_sim` del mismo día
      sigue vigente (como `--run-once` del worker).

    Con `--simulate` la corrida pasa por `app.worker.runner.run_job(..., simulated=True)` (S4A-D89):
    el runner reclama `expirations_sim`, fija el reloj solo dentro de la corrida y atribuye la
    auditoría al usuario técnico; por eso `--simulate` con `--as` sale con 2. Sin `--simulate` no
    se toca `worker.job_runs`.
    """
    settings = get_settings()
    opciones = runtime_options(ctx)
    objetivo = _recompute_target(settings, opciones, on_date, simulate=simulate, actor=actor)
    if simulate:
        typer.echo(f"RELOJ SIMULADO: {objetivo.isoformat()}")
    conteos, codigo = _run(_recompute(settings, opciones, objetivo, simulate, actor))
    texto = " ".join(f"{clave}={conteos.get(clave, 0)}" for clave in RECOMPUTE_KEYS)
    typer.echo(f"recompute-memberships: {texto}")
    raise typer.Exit(code=codigo)


RECOMPUTE_KEYS: Final = (
    "revisados",
    "cambiadas",
    "por_vencer",
    "vencidas",
    "otras",
    "busy_omitidos",
    "errores",
)
"""Los conteos de `RecomputeSummary` que imprime `recompute-memberships`, en orden."""
EXIT_BY_SIMULATED_RESULT: Final = {"ok": 0, "error": 1, "running": 3}
SIMULATE_WITH_AS_REJECTED: Final = (
    "--simulate no admite --as: la corrida simulada se atribuye al usuario técnico"
)
"""S4A-D89 (revisión de seguridad de B2, L-1): el runner fija `SYSTEM_USER_ID`; aceptar `--as`
dejaría creer que la auditoría simulada va a nombre de esa persona."""


def _reject(mensaje: str, comando: str = "recompute-memberships") -> NoReturn:
    typer.echo(f"{comando}: {mensaje}", err=True)
    raise typer.Exit(code=2)


def production_guard_error(
    settings: Settings, opciones: RuntimeOptions, actor: str | None
) -> str | None:
    """S4A-D53: con `ENV=production` un comando que escribe exige `--as` y rechaza
    `--db-timeouts off`; `None` si se puede seguir."""
    if settings.ENV != "production":
        return None
    if actor is None:
        return "--as <correo> es obligatorio con ENV=production"
    if not opciones.db_timeouts:
        return "--db-timeouts off no se acepta con ENV=production"
    return None


def _recompute_target(
    settings: Settings,
    opciones: RuntimeOptions,
    on_date: str | None,
    *,
    simulate: bool,
    actor: str | None,
) -> date:
    """El día del recálculo, o salida 2: fecha inválida, `--simulate` con `--as` (S4A-D89),
    producción sin `--as` o con `--db-timeouts off` (S4A-D53), o la guarda de `--date` y
    `--simulate` (S4A-D48, E5)."""
    from app.core.clock import current_clock
    from app.worker.runtime import clock_override_error, simulation_error

    try:
        pedido = date.fromisoformat(on_date) if on_date is not None else None
    except ValueError:
        _reject("--date inválida (use AAAA-MM-DD)")
    if simulate and actor is not None:
        _reject(SIMULATE_WITH_AS_REJECTED)
    if (rechazo_prod := production_guard_error(settings, opciones, actor)) is not None:
        _reject(rechazo_prod)
    hoy = current_clock().today_bogota()
    objetivo = pedido or hoy
    rechazo = clock_override_error(objetivo, hoy, simulate=simulate, settings=settings)
    if rechazo is None and simulate:
        rechazo = simulation_error(settings)
    if rechazo is not None:
        _reject(rechazo)
    return objetivo


async def _recompute(
    settings: Settings,
    options: RuntimeOptions,
    objetivo: date,
    simulate: bool,
    actor_email: str | None,
) -> tuple[dict[str, Any], int]:
    """`(conteos, código de salida)`; sale con 2 (por `resolve_actor`) si `--as` no sirve."""
    from app.core import db
    from app.modules.memberships.service import recompute_statuses

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        if simulate:
            return await _recompute_simulated(db.get_sessionmaker(), objetivo)
        # El actor debe seguir fijado durante cada commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            resumen = await recompute_statuses(db.get_sessionmaker(), today=objetivo)
    conteos = asdict(resumen)
    return conteos, 1 if resumen.busy_omitidos + resumen.errores else 0


async def _recompute_simulated(session_factory: Any, objetivo: date) -> tuple[dict[str, Any], int]:
    """La corrida simulada por el runner del worker (S4A-D89): reclama `expirations_sim` con el
    reloj a las 12:00 de Bogotá de `objetivo`; nunca la fila real del día."""
    from zoneinfo import ZoneInfo

    from app.core.clock import FrozenClock
    from app.worker.registry import get_registry
    from app.worker.runner import run_job
    from app.worker.schedule import WORKER_TIMEZONE

    spec = next(s for s in get_registry() if s.name == "expirations")
    zona = ZoneInfo(WORKER_TIMEZONE)
    reloj = FrozenClock(datetime(objetivo.year, objetivo.month, objetivo.day, 12, tzinfo=zona))
    salida = await run_job(spec, clock=reloj, session_factory=session_factory, simulated=True)
    return dict(salida.details), EXIT_BY_SIMULATED_RESULT.get(salida.result, 1)


VERIFY_LOCK_POLL_S: Final = 2.0
"""Espera entre intentos de `pg_try_advisory_lock` de `verify-audit` (S4A-D15)."""


@app.command("verify-audit")
def verify_audit(
    ctx: typer.Context,
    actor: Annotated[str | None, typer.Option("--as")] = None,
    wait_timeout: Annotated[int, typer.Option("--wait-timeout", min=0)] = 300,
) -> None:
    """Verifica la cadena de auditoría (S4A-B3, US-105; S4A-D15, S4A-D43, S4A-D44, S4A-D53).

    - toma el candado `4_270_003` con `pg_try_advisory_lock` cada `VERIFY_LOCK_POLL_S` segundos
      hasta `--wait-timeout` (por `audit.service.acquire_verify_lock`: conexión `AUTOCOMMIT` que
      `release_verify_lock` invalida al terminar);
    - corre `core.audit_verify.run_verification(session, source="cli", by=actor)` bajo
      `unit_of_work(actor)` (`--as`, o `SYSTEM_USER_ID` sin él) y confirma;
    - imprime `format_verify_message` (nunca `before` ni `after`) y sale 0 (íntegra) o 1 (rota);
    - sale 2 si `--as` no sirve, si la base no responde (mensaje genérico, sin URL ni contraseña),
      si `--wait-timeout` se agota, o con `ENV=production` sin `--as` o con `--db-timeouts off`.
    """
    from sqlalchemy.exc import SQLAlchemyError

    settings = get_settings()
    opciones = runtime_options(ctx)
    if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
        _reject(rechazo, "verify-audit")
    try:
        texto, codigo = _run(_verify_audit(settings, opciones, actor, wait_timeout))
    except (OSError, SQLAlchemyError):
        _reject("la base de datos no responde", "verify-audit")
    typer.echo(texto)
    raise typer.Exit(code=codigo)


async def _verify_audit(
    settings: Settings, options: RuntimeOptions, actor_email: str | None, wait_timeout: int
) -> tuple[str, int]:
    """`(mensaje, código)`: espera el candado, verifica bajo el actor y confirma."""
    from app.core.audit_verify import format_verify_message, run_verification
    from app.modules.audit.service import release_verify_lock

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        conn = await _wait_verify_lock(wait_timeout)
        try:
            with unit_of_work(actor):
                async with session.begin():
                    vista = await run_verification(session, source="cli", by=actor)
        finally:
            await release_verify_lock(conn)
    return format_verify_message(vista)


async def _wait_verify_lock(wait_timeout: int) -> Any:
    """La conexión del candado `4_270_003` (`AUTOCOMMIT`), reintentando cada
    `VERIFY_LOCK_POLL_S` segundos; sale con 2 si `wait_timeout` se agota."""
    import asyncio
    import time

    from app.modules.audit.service import acquire_verify_lock

    limite = time.monotonic() + wait_timeout
    while (conn := await acquire_verify_lock()) is None:
        restante = limite - time.monotonic()
        if restante <= 0:
            _reject("otra verificación sigue en curso (--wait-timeout agotado)", "verify-audit")
        await asyncio.sleep(min(VERIFY_LOCK_POLL_S, restante))
    return conn


if __name__ == "__main__":
    app()
