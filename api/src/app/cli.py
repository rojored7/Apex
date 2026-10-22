"""Comandos del api (`python -m app.cli`; en Compose, `docker compose run --rm tools <cmd>`).

- `export-openapi <ruta>` (US-021): construye `create_app()` con una configuración de
  exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON
  con claves ordenadas, sangría de 2 y salto de línea final. `info.version` es la versión
  del paquete, no `APP_VERSION`, para que la salida no cambie con cada commit. No escribe
  en tablas, así que no necesita actor.

Comandos siguientes: `init-keys` (US-023), `seed --as` (US-041), `import-members`,
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
    """`--as <email>` → id de esa persona (no dada de baja); sin `--as`, el usuario técnico."""
    if email is None:
        return SYSTEM_USER_ID
    from app.modules.auth.service import active_admin_id_by_email

    quien = await active_admin_id_by_email(session, email)
    if quien is None:
        typer.echo(f"--as: no existe un usuario con ese correo ({email})", err=True)
        raise typer.Exit(code=2)
    return quien


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


async def _seed(settings: Settings, actor_email: str | None) -> str:
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
                    assert settings.ADMIN_EMAIL is not None  # noqa: S101 - validado antes
                    assert settings.ADMIN_INITIAL_PASSWORD is not None  # noqa: S101
                    resultado = await seed_admin(
                        session,
                        settings.ADMIN_EMAIL,
                        settings.ADMIN_INITIAL_PASSWORD.get_secret_value(),
                        by=actor,
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
def seed(actor: Annotated[str | None, typer.Option("--as")] = None) -> None:
    """Crea el primer admin activo con ADMIN_EMAIL y ADMIN_INITIAL_PASSWORD (idempotente).

    Sale con 2 si falta el correo, falta la contraseña o es débil; nunca imprime la contraseña.
    """

    from app.core.security import WeakPasswordError, validate_password_policy
    from app.modules.auth.exceptions import AuthError

    settings = get_settings()
    if not settings.ADMIN_EMAIL or settings.ADMIN_INITIAL_PASSWORD is None:
        typer.echo("seed: faltan ADMIN_EMAIL o ADMIN_INITIAL_PASSWORD en el entorno", err=True)
        raise typer.Exit(code=2)
    try:
        validate_password_policy(settings.ADMIN_INITIAL_PASSWORD.get_secret_value())
    except WeakPasswordError as error:
        typer.echo(f"seed: ADMIN_INITIAL_PASSWORD no cumple la política ({error.reason})", err=True)
        raise typer.Exit(code=2) from None
    try:
        resultado = _run(_seed(settings, actor))
    except AuthError as error:
        typer.echo(f"seed: {error.code}", err=True)
        raise typer.Exit(code=2) from None
    if resultado == "created":
        typer.echo("seed: admin inicial creado")
    else:
        typer.echo("seed: omitido: ya existe un admin activo")


if __name__ == "__main__":
    app()
