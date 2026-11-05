"""Respaldo de la KEK: `export-kek`, `verify-kek-backup` y `restore-kek` (S4B-B3a, US-116;
S4B-D58, D62, D74, D85).

- `export-kek --out <archivo> --as <correo>`: cifra la KEK con `age -p` (la frase la pide `age` por
  la terminal; APEX no la ve). Solo con `CRYPTO_PROVIDER=local`. Escribe una fila de `crypto_ops`
  (`export`, `kek.backup`) y una entrada de auditoría `export` sobre `crypto.crypto_keys`.
- `verify-kek-backup <archivo> [--as <correo>]` (S5-D187): abre el respaldo en memoria, prueba
  `unwrap` de cada DEK `local` `active`/`decrypt_only` (las de OpenBao no) y, si el archivo de la
  KEK existe, compara en tiempo constante con él (con cero filas `local` esa comparación es
  obligatoria); no escribe la KEK. Salida `verify-kek-backup: total=N failed=M`; 0 todo ok, 1 alguna
  DEK sin abrir, KEK distinta o nada que comprobar, 2 archivo inválido o uso.
- `restore-kek <archivo> --out <ruta> --as <correo>`: descifra el respaldo hacia un archivo nuevo
  (0o600). Corre aunque la KEK viva falte y tolera la base caída: avisa "sin bitácora" y sale 0.
  Deja `export` con `purpose = restore` y `after = {"op": "restore"}`.

Usan el preámbulo de lectura-escritura de `cli_base` (nunca el que carga proveedor y llaves,
S4B-D62: restaurar es la operación para cuando la KEK no está y no debe crear llaves con una KEK
equivocada). Ninguna salida repite la KEK, una frase, una ruta ni el texto de `age`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn
from uuid import UUID

import typer
from sqlalchemy.exc import OperationalError

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    cli_runtime,
    production_guard_error,
    reject,
    resolve_admin_actor,
    runtime_options,
    unit_of_work,
)
from app.core import audit
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto import archive, oplog
from app.core.crypto.archive import (
    AgeError,
    KekPathRejected,
    NoTty,
    VerifyKekResult,
)
from app.core.crypto.errors import CryptoError
from app.core.crypto.kek_backup import load_wrapped

DATA_CLASS = "kek.backup"
AUDIT_TABLE = "crypto.crypto_keys"
NOT_LOGGED = "sin bitácora (la base no está disponible); anótelo a mano"
LOG_FAILED = "archivo restaurado pero SIN bitácora: registre a mano (RUNBOOK §12)"
OPEN_FAILED = "no se pudo abrir el respaldo"
Verb = Literal["export", "verify"]
CONNECTION_ERRORS = (OperationalError, OSError, TimeoutError)
"""Lo único que degrada `restore-kek` a "sin bitácora" al resolver al actor (S4B-D130, L1)."""


class LogFailed(Exception):
    """El archivo ya existe, pero la bitácora no se pudo escribir (solo `export-kek`)."""


def _fail(error: Exception, command: str, *, writing: bool = False) -> NoReturn:
    """Traduce un error del respaldo a un mensaje fijo y salida 2; el resto se re-lanza."""
    if isinstance(error, FileExistsError):
        reject("el archivo de salida ya existe", command)
    if isinstance(error, KekPathRejected):
        reject("la ruta de salida no es válida", command)
    if isinstance(error, CryptoError):
        reject("la KEK no está disponible", command)
    if isinstance(error, NoTty):
        reject("se requiere una terminal interactiva (age pide la frase por la terminal)", command)
    if isinstance(error, archive.AgeTimeout):
        reject("age superó el plazo y se canceló", command)
    if isinstance(error, archive.AgeMissing):
        reject("age no está disponible en este equipo", command)
    if isinstance(error, (AgeError, OSError)):
        reject("no se pudo escribir la KEK cifrada" if writing else OPEN_FAILED, command)
    raise error


async def _record(
    session: Any,
    actor_id: UUID,
    *,
    verb: Verb,
    purpose: str | None,
    result: str,
    after: dict[str, object],
) -> None:
    """Fila de `crypto_ops` y entrada de auditoría en la misma transacción (sin material)."""
    with unit_of_work(actor_id):
        async with session.begin():
            oplog.record(
                verb,
                data_class=DATA_CLASS,
                key_id=None,
                key_version=None,
                purpose=purpose,
                result=result,
            )
            await audit.record(
                session,
                action=verb,
                table_name=AUDIT_TABLE,
                record_id=None,
                before=None,
                after=after,
                user_id=actor_id,
            )


async def _export(
    settings: Settings, options: RuntimeOptions, out: Path, actor: str | None
) -> None:
    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=True)
        kek_path = settings.CRYPTO_LOCAL_KEK_PATH
        if kek_path is None:
            raise CryptoError("kek_missing", "la KEK no está disponible")
        archive.export_kek_file(kek_path, out)
        try:
            await _record(
                session, actor_id, verb="export", purpose=None, result="ok", after={"op": "export"}
            )
        except Exception:
            raise LogFailed from None


async def _verify(
    settings: Settings, options: RuntimeOptions, file: Path, actor: str | None
) -> VerifyKekResult:
    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=False)
            wrapped = await load_wrapped(session)
        try:
            resultado = archive.verify_kek_backup(
                file, wrapped, current_kek_path=settings.CRYPTO_LOCAL_KEK_PATH
            )
        except AgeError:
            await _record(
                session,
                actor_id,
                verb="verify",
                purpose=None,
                result="error",
                after={"op": "verify"},
            )
            raise
        detalle: dict[str, object] = {
            "op": "verify",
            "total": resultado.total,
            "failed": len(resultado.failed_key_ids),
            "file_matches": resultado.file_matches if resultado.file_checked else None,
        }
        await _record(
            session,
            actor_id,
            verb="verify",
            purpose=None,
            result="ok"
            if resultado.ok and (resultado.total or resultado.file_checked)
            else "error",
            after=detalle,
        )
        return resultado


async def _resolve_if_db_up(
    settings: Settings, options: RuntimeOptions, actor: str | None
) -> UUID | None:
    """El admin de `--as`, o `None` si la base no responde (`restore-kek` sigue sin bitácora)."""
    try:
        async with cli_runtime(settings, options) as session:
            async with session.begin():
                return await resolve_admin_actor(session, actor, required=True)
    except typer.Exit:
        raise
    except CONNECTION_ERRORS:
        return None


async def _log_restore(settings: Settings, options: RuntimeOptions, actor_id: UUID) -> bool:
    try:
        async with cli_runtime(settings, options) as session:
            await _record(
                session,
                actor_id,
                verb="export",
                purpose="restore",
                result="ok",
                after={"op": "restore"},
            )
    except Exception:
        return False
    return True


RestoreOutcome = Literal["logged", "db_down", "log_failed"]


async def _restore(
    settings: Settings, options: RuntimeOptions, file: Path, out: Path, actor: str | None
) -> RestoreOutcome:
    """Restaura la KEK: `logged`; `db_down` (base caída, D124, sale 0); `log_failed` (base arriba
    pero sin rastro, S4B-D207, sale 1)."""
    actor_id = await _resolve_if_db_up(settings, options, actor)
    archive.restore_kek_file(file, out)
    if actor_id is None:
        return "db_down"
    return "logged" if await _log_restore(settings, options, actor_id) else "log_failed"


def _prelude(
    ctx: typer.Context, command: str, actor: str | None
) -> tuple[Settings, RuntimeOptions]:
    settings = cli_base.get_settings()  # por el módulo: las pruebas lo reemplazan (S4B-D29)
    opciones = runtime_options(ctx)
    if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
        reject(rechazo, command)
    return settings, opciones


def _register_export(app: typer.Typer) -> None:
    @app.command("export-kek")
    def export_kek_command(
        ctx: typer.Context,
        out: Annotated[Path, typer.Option("--out", help="Archivo nuevo para la KEK cifrada.")],
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Exporta la KEK cifrada con `age -p` (la frase la pide `age` por la terminal)."""
        settings, opciones = _prelude(ctx, "export-kek", actor)
        if settings.CRYPTO_PROVIDER != "local":
            reject(
                "solo con CRYPTO_PROVIDER=local (la KEK de OpenBao no sale del KMS)", "export-kek"
            )
        try:
            _run(_export(settings, opciones, out, actor))
        except typer.Exit:
            raise
        except LogFailed:
            typer.echo("export-kek: el archivo se creó pero NO quedó en la bitácora", err=True)
            raise typer.Exit(code=1) from None
        except Exception as error:
            _fail(error, "export-kek", writing=True)
        typer.echo(
            "export-kek: KEK cifrada con age; guarde la frase y el archivo en lugares distintos"
        )


def _register_verify(app: typer.Typer) -> None:
    @app.command("verify-kek-backup")
    def verify_kek_backup_command(
        ctx: typer.Context,
        file: Annotated[Path, typer.Argument(help="Respaldo de la KEK hecho con export-kek.")],
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Comprueba que el respaldo abre las DEK de la base (sin escribir la KEK)."""
        settings, opciones = _prelude(ctx, "verify-kek-backup", actor)
        try:
            resultado = _run(_verify(settings, opciones, file, actor))
        except typer.Exit:
            raise
        except Exception as error:
            _fail(error, "verify-kek-backup")
        fallidas = len(resultado.failed_key_ids)
        typer.echo(f"verify-kek-backup: total={resultado.total} failed={fallidas}")
        sin_nada = resultado.total == 0 and not resultado.file_checked
        if sin_nada:
            typer.echo("verify-kek-backup: no hay KEK en el archivo con qué comparar", err=True)
        for key_id in resultado.failed_key_ids:
            typer.echo(f"verify-kek-backup: no abre la llave {key_id}", err=True)
        if resultado.file_checked:
            veredicto = "coincide" if resultado.file_matches else "no coincide"
            typer.echo(
                f"verify-kek-backup: {veredicto} con la KEK del archivo",
                err=not resultado.file_matches,
            )
        if fallidas or sin_nada or not resultado.file_matches:
            raise typer.Exit(code=1)


def _register_restore(app: typer.Typer) -> None:
    @app.command("restore-kek")
    def restore_kek_command(
        ctx: typer.Context,
        file: Annotated[Path, typer.Argument(help="Respaldo de la KEK hecho con export-kek.")],
        out: Annotated[Path, typer.Option("--out", help="Archivo nuevo para la KEK en claro.")],
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Restaura la KEK desde el respaldo (corre aunque la KEK viva falte)."""
        settings, opciones = _prelude(ctx, "restore-kek", actor)
        try:
            resultado = _run(_restore(settings, opciones, file, out, actor))
        except typer.Exit:
            raise
        except Exception as error:
            _fail(error, "restore-kek")
        typer.echo("restore-kek: KEK restaurada en el archivo indicado (modo 600)")
        if resultado == "log_failed":
            typer.echo(f"restore-kek: {LOG_FAILED}", err=True)
            raise typer.Exit(1)
        if resultado == "db_down":
            typer.echo(f"restore-kek: {NOT_LOGGED}", err=True)
            aviso = {
                "event": "restore_sin_bitacora",
                "actor": actor,
                "ts": current_clock().now_utc().isoformat(),
            }
            typer.echo(json.dumps(aviso), err=True)


def register(app: typer.Typer) -> None:
    _register_export(app)
    _register_verify(app)
    _register_restore(app)
