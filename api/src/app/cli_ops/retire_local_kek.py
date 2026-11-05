"""`retire-local-kek --as <correo> [--yes] [--manifest RUTA]` (S5-B2; S5-D73, D186, D190).

Borra el archivo de la KEK local (`CRYPTO_LOCAL_KEK_PATH`) cuando ya no queda nada envuelto con
ella. Orden: ninguna fila `encrypt|index` en `local` (`QUEDAN_LOCAL`); si el archivo ya no está,
`ya estaba retirada` (salida 0, sin segunda auditoría); las pruebas de custodia; la palabra
`RETIRAR` o `--yes`. Todo bajo el candado `apex:rotate:kek` (S5-D190), que excluye a `rotate-kek`,
`--trim` y `migrate-provider`. Dentro de la transacción de la auditoría se REPITE la comprobación
de filas; la auditoría `{kek_local: retirada}` (`record_id` nulo, sin `crypto_ops`) se confirma
primero y SOLO después se hace `unlink`; si falla, sale 1 (`repita el comando`) y la auditoría
queda. La llave de firma local no se toca.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.cli_manifest import CustodyRejected, confirmation_error, custody_errors, custody_proofs
from app.core import audit, db
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto import migration, rotation
from app.core.crypto.migration import SessionFactory

COMMAND = "retire-local-kek"
DEFAULT_MANIFEST = Path("/data/backups/latest.json")
QUEDAN_LOCAL = "quedan llaves envueltas con la KEK local; ejecute migrate-provider antes"
UNLINK_FALLO = "no se pudo borrar el archivo de la KEK local; repita el comando"


@dataclass(frozen=True)
class Pedido:
    actor: str | None
    yes: bool
    manifest: Path


async def _auditar(session: AsyncSession, fabrica: SessionFactory, actor_id: UUID) -> None:
    with unit_of_work(actor_id):
        async with session.begin():
            if await migration.verify_provider(fabrica, expected="openbao"):
                reject(QUEDAN_LOCAL, COMMAND)  # se repite DENTRO de la transacción (S5-D190)
            await audit.record(
                session,
                action="update",
                table_name="crypto.crypto_keys",
                record_id=None,
                before=None,
                after={"kek_local": "retirada"},
                user_id=actor_id,
            )


def _borrar(kek: Path) -> None:
    """`unlink` solo después de confirmar la auditoría; si falla, la auditoría queda."""
    try:
        os.unlink(kek)
    except OSError:
        typer.echo(f"{COMMAND}: {UNLINK_FALLO}", err=True)
        raise typer.Exit(code=1) from None


async def _retire(settings: Settings, opciones: RuntimeOptions, p: Pedido) -> None:
    async with cli_runtime(settings, opciones) as session:
        fabrica = db.get_sessionmaker()
        async with session.begin():
            actor_id = await resolve_admin_actor(session, p.actor, required=True)
        with custody_errors(COMMAND):
            async with rotation.kek_lock(fabrica):
                if await migration.verify_provider(fabrica, expected="openbao"):
                    reject(QUEDAN_LOCAL, COMMAND)
                kek = settings.CRYPTO_LOCAL_KEK_PATH
                if kek is None or not kek.exists():
                    typer.echo(f"{COMMAND}: la KEK local ya estaba retirada")
                    return
                try:
                    now = current_clock().now_utc()
                    await custody_proofs(session, settings, p.manifest, now=now)
                except CustodyRejected as error:
                    reject(str(error), COMMAND)
                if (rechazo := confirmation_error("RETIRAR", yes=p.yes)) is not None:
                    reject(rechazo, COMMAND)
                await _auditar(session, fabrica, actor_id)
                _borrar(kek)
        typer.echo(f"{COMMAND}: KEK local retirada")


def register(app: typer.Typer) -> None:
    @app.command("retire-local-kek")
    def retire_local_kek_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
        yes: Annotated[bool, typer.Option("--yes")] = False,
        manifest: Annotated[Path, typer.Option("--manifest")] = DEFAULT_MANIFEST,
    ) -> None:
        """Borra `kek.bin` del volumen `keys` cuando ya no queda nada envuelto con ella."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        _run(_retire(settings, opciones, Pedido(actor, yes, manifest)))
