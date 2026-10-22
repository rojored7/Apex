"""Comandos del api (`python -m app.cli`; en Compose, `docker compose run --rm tools <cmd>`).

- `export-openapi <ruta>` (US-021): construye `create_app()` con una configuración de
  exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON
  con claves ordenadas, sangría de 2 y salto de línea final. `info.version` es la versión
  del paquete, no `APP_VERSION`, para que la salida no cambie con cada commit. No escribe
  en tablas, así que no necesita actor.

Comandos siguientes: `init-keys` (US-023), `seed --as` (US-041), `issue-reset-link --as`
(S2-B4, L-13), `unlock-user [--as]` (S2-B5), `import-members`,
`rotate-key`, `sign-audit`. Todo comando que escriba tablas acepta `--as <email>` (N-15).
"""

from __future__ import annotations

import json
import os
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any
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


@app.callback()
def main() -> None:
    """Comandos de APEX. Con un solo comando, Typer exige el callback para usar subcomandos."""


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


async def _seed(
    settings: Settings,
    admin_email: str,
    admin_password: str,
    actor_email: str | None,
    *,
    force_change: bool,
) -> str:
    from app.core import db
    from app.core.audit import install_audit_listeners
    from app.core.crypto.oplog import install_oplog_listeners
    from app.core.crypto.types import install_crypto_type_listeners
    from app.core.security import configure_password_hasher, configure_password_policy
    from app.modules.auth.service import seed_admin

    install_audit_listeners()
    install_oplog_listeners()
    install_crypto_type_listeners()
    configure_password_hasher(
        settings.ARGON2_TIME_COST, settings.ARGON2_MEMORY_COST_KIB, settings.ARGON2_PARALLELISM
    )
    configure_password_policy(settings.PASSWORD_MIN_LENGTH)
    db.configure_engine(db.create_engine_from(settings))
    try:
        async with db.get_sessionmaker()() as session:
            async with session.begin():
                actor = await resolve_actor(session, actor_email)
            # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
            with unit_of_work(actor):
                async with session.begin():
                    resultado = await seed_admin(
                        session, admin_email, admin_password, by=actor, force_change=force_change
                    )
        return resultado.outcome
    finally:
        await db.dispose_engine()


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, o un hilo con su propio loop si ya hay uno activo (pruebas async)."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        return ejecutor.submit(asyncio.run, coro).result()


@app.command("seed")
def seed(
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
            _seed(settings, semilla.ADMIN_EMAIL, clave, actor, force_change=not no_force_change)
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
    salida = _run(_issue_reset_link(settings, email, actor))
    if salida is None:
        typer.echo(_LINK_REJECTED, err=True)
        raise typer.Exit(code=2)
    url, purpose, expires_at = salida
    typer.echo(f"issue-reset-link: enlace de {purpose} válido hasta {expires_at}")
    typer.echo(url)


# El mismo texto para un correo inexistente, borrado o no elegible: no revela si existe.
_LINK_REJECTED = "issue-reset-link: esa cuenta no puede recibir un enlace"


async def _issue_reset_link(
    settings: Settings, email: str, actor_email: str
) -> tuple[str, str, str] | None:
    """`(url, propósito, vence)` o `None` si la cuenta no existe o no es elegible. Sale con 2
    (por `resolve_actor` o aquí) si `--as` no es un admin activo."""
    from app.core import db
    from app.core.audit import install_audit_listeners
    from app.core.crypto.oplog import install_oplog_listeners
    from app.core.crypto.types import install_crypto_type_listeners
    from app.modules.auth.exceptions import UserNotEligible, UserNotFound
    from app.modules.auth.service import (
        active_admin_id_by_email,
        ids_by_email,
        issue_link,
        normalize_login_email,
    )

    install_audit_listeners()
    install_oplog_listeners()
    install_crypto_type_listeners()
    db.configure_engine(db.create_engine_from(settings))
    try:
        async with db.get_sessionmaker()() as session:
            async with session.begin():
                actor = await resolve_actor(session, actor_email)
                if await active_admin_id_by_email(session, actor_email) != actor:
                    typer.echo("--as: debe ser un admin activo", err=True)
                    raise typer.Exit(code=2)
                objetivo = (await ids_by_email(session, [email])).get(normalize_login_email(email))
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
    finally:
        await db.dispose_engine()


@app.command("unlock-user")
def unlock_user(
    email: str,
    actor: Annotated[str | None, typer.Option("--as")] = None,
) -> None:
    """Desbloquea la cuenta de `email` (S2-B5, US-050; S2-D10): limpia `locked_at` y
    `failed_login_count` con `service.unlock` y deja el `update` auditado con el actor de `--as`
    o, sin él, `SYSTEM_USER_ID`. Corre en otro proceso que el api: los contadores en memoria del
    api se limpian con `up -d api` (docs/RUNBOOK.md). Sale con 2, con el mismo mensaje y sin
    repetir el correo, si la cuenta no existe, está borrada o no está bloqueada.
    """
    settings = get_settings()
    if not _run(_unlock_user(settings, email, actor)):
        typer.echo(_UNLOCK_REJECTED, err=True)
        raise typer.Exit(code=2)
    typer.echo("unlock-user: cuenta desbloqueada")


# El mismo texto para una cuenta no bloqueada, inexistente o borrada: no revela si existe.
_UNLOCK_REJECTED = "unlock-user: no hay una cuenta bloqueada con ese correo"


async def _unlock_user(settings: Settings, email: str, actor_email: str | None) -> bool:
    """`True` si desbloqueó; `False` si la cuenta no existe, está borrada o no está bloqueada.
    Sale con 2 (por `resolve_actor`) si `--as` no es una persona activa."""
    from app.core import db
    from app.core.audit import install_audit_listeners
    from app.core.crypto.oplog import install_oplog_listeners
    from app.core.crypto.types import install_crypto_type_listeners
    from app.modules.auth.exceptions import NotLocked, UserNotFound
    from app.modules.auth.service import ids_by_email, normalize_login_email, unlock

    install_audit_listeners()
    install_oplog_listeners()
    install_crypto_type_listeners()
    db.configure_engine(db.create_engine_from(settings))
    try:
        async with db.get_sessionmaker()() as session:
            async with session.begin():
                actor = await resolve_actor(session, actor_email)
                objetivo = (await ids_by_email(session, [email])).get(normalize_login_email(email))
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
    finally:
        await db.dispose_engine()


if __name__ == "__main__":
    app()
