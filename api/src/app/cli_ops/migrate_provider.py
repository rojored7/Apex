"""`migrate-provider --from local --to openbao [--as] [--dry-run] [--yes] [--verify]` (S5-B2).

Mueve la envoltura de cada DEK `encrypt|index` de un proveedor a otro (S5-D18, D183); reanudable y
sin keyring. `--verify` (solo lectura, ubicación, no apertura) imprime `fuera_de_destino=N`, sale 1
si N > 0; el plan imprime `total=N`; `--dry-run` termina ahí. Para escribir exige las
pruebas de custodia (S5-D186), `MIGRAR` o `--yes` y el candado `apex:rotate:kek` (S5-D190). Un fallo
sale 1 (`repita el comando`) sin texto del proveedor y se audita con `failed: true` (S5-D189).
"""

from __future__ import annotations

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
from app.cli_manifest import (
    CustodyRejected,
    confirmation_error,
    custody_errors,
    custody_proofs,
    exit_after_failure,
)
from app.core import audit, db
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto import migration, rotation
from app.core.crypto import provider as provider_mod
from app.core.crypto.migration import SessionFactory
from app.core.crypto.provider import ProviderResolver

COMMAND = "migrate-provider"
AUDIT_TABLE = "crypto.crypto_keys"
DEFAULT_MANIFEST = Path("/data/backups/latest.json")
PARES = {("local", "openbao"), ("openbao", "local")}


@dataclass(frozen=True)
class Pedido:
    origen: str
    destino: str
    actor: str | None
    dry_run: bool
    yes: bool
    verify: bool
    manifest: Path


async def _migrate(settings: Settings, opciones: RuntimeOptions, p: Pedido) -> None:
    resolver = provider_mod.make_resolver(settings)
    async with cli_runtime(settings, opciones) as session:
        fabrica = db.get_sessionmaker()
        async with session.begin():
            actor_id = await resolve_admin_actor(session, p.actor, required=True)
        if p.verify:
            fuera = await migration.verify_provider(fabrica, expected=p.destino)
            typer.echo(f"{COMMAND}: fuera_de_destino={fuera}")
            raise typer.Exit(code=1 if fuera else 0)
        previa = await migration.migrate_provider(
            fabrica, from_=p.origen, to=p.destino, resolver=resolver, actor=actor_id, dry_run=True
        )
        if previa.total == 0:
            typer.echo(f"{COMMAND}: nada que migrar")
            return
        typer.echo(f"{COMMAND}: total={previa.total}")
        if p.dry_run:
            typer.echo(f"{COMMAND}: dry-run: no se escribió nada")
            return
        await _exigir(session, settings, p)
        with custody_errors(COMMAND):
            async with rotation.kek_lock(fabrica):
                resultado = await _escribir(session, fabrica, resolver, p, actor_id)
        typer.echo(f"{COMMAND}: hecho={resultado.done}/{resultado.total}")
        if resultado.failed_key_id is not None:
            exit_after_failure(COMMAND, resultado)
        typer.echo(f"{COMMAND}: migración completa")


async def _exigir(session: AsyncSession, settings: Settings, p: Pedido) -> None:
    try:
        await custody_proofs(session, settings, p.manifest, now=current_clock().now_utc())
    except CustodyRejected as error:
        reject(str(error), COMMAND)
    if (rechazo := confirmation_error("MIGRAR", yes=p.yes)) is not None:
        reject(rechazo, COMMAND)


async def _escribir(
    session: AsyncSession,
    fabrica: SessionFactory,
    resolver: ProviderResolver,
    p: Pedido,
    actor_id: UUID,
) -> migration.MigrationResult:
    with unit_of_work(actor_id):
        resultado = await migration.migrate_provider(
            fabrica, from_=p.origen, to=p.destino, resolver=resolver, actor=actor_id
        )
        detalle: dict[str, object] = {"from": p.origen, "to": p.destino}
        detalle |= {"total": resultado.total, "done": resultado.done}
        if resultado.failed_key_id is not None:
            detalle["failed"] = True  # el fallo parcial también queda auditado (S5-D189)
        async with session.begin():
            await audit.record(
                session,
                action="update",
                table_name=AUDIT_TABLE,
                record_id=resultado.job_id,
                before=None,
                after=detalle,
                user_id=actor_id,
            )
    return resultado


def register(app: typer.Typer) -> None:
    @app.command("migrate-provider")
    def migrate_provider_command(
        ctx: typer.Context,
        origen: Annotated[str, typer.Option("--from")] = "local",
        destino: Annotated[str, typer.Option("--to")] = "openbao",
        actor: Annotated[str | None, typer.Option("--as")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
        yes: Annotated[bool, typer.Option("--yes")] = False,
        verify: Annotated[bool, typer.Option("--verify")] = False,
        manifest: Annotated[Path, typer.Option("--manifest")] = DEFAULT_MANIFEST,
    ) -> None:
        """Migra las llaves envueltas de un proveedor a otro (reanudable)."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        if (origen, destino) not in PARES:
            reject("--from/--to deben ser local y openbao (en cualquier sentido)", COMMAND)
        pedido = Pedido(origen, destino, actor, dry_run, yes, verify, manifest)
        _run(_migrate(settings, opciones, pedido))
