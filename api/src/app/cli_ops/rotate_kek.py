"""`rotate-kek [--trim] --as <correo> [--manifest RUTA]` (S5-B2; S5-D19, D184).

Sin `--trim`: rota la KEK de OpenBao (salvo que una rotación anterior haya quedado a medias) y
re-envuelve cada DEK con `unwrap` + `wrap` (S5-D55a); reanudable. Imprime `version=V`, `total=N`,
`hecho=D/N` y `llaves re-envueltas`; un fallo sale 1 (`repita el comando`) sin texto del proveedor.
Audita `update` sobre `crypto.crypto_keys` con `{event: rotate_kek, version, total, done}`.

Con `--trim` (irreversible): exige `trim_ready`, un respaldo con instantánea POSTERIOR al fin del
re-envuelto y la palabra `RECORTAR`; sube `min_decryption_version` (nunca `/trim`) y audita
`{event: trim_kek, min_decryption_version}`. En ambos casos, antes, las pruebas de custodia
(S5-D186). Vive en un solo archivo porque Typer no admite dos comandos con el mismo nombre y los
archivos de `cli_ops/` no se importan entre sí (S5-D184, amplía S5-D97).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
from app.core.crypto import provider as provider_mod
from app.core.crypto import rotation
from app.core.crypto.migration import SessionFactory
from app.core.crypto.provider import ProviderResolver

COMMAND = "rotate-kek"
AUDIT_TABLE = "crypto.crypto_keys"
DEFAULT_MANIFEST = Path("/data/backups/latest.json")
TRIM_NO_LISTO = "aún hay llaves sin re-envolver con la última versión de la KEK"
TRIM_CAMBIO = "la KEK o las envolturas cambiaron desde la comprobación; repita la comprobación"
SIN_SNAPSHOT_POSTERIOR = "el respaldo con instantánea de OpenBao es anterior a la rotación"


@dataclass(frozen=True)
class Pedido:
    actor: str | None
    trim: bool
    manifest: Path


async def _auditar(
    session: AsyncSession, actor_id: UUID, record_id: UUID | None, detalle: dict[str, object]
) -> None:
    async with session.begin():
        await audit.record(
            session,
            action="update",
            table_name=AUDIT_TABLE,
            record_id=record_id,
            before=None,
            after=detalle,
            user_id=actor_id,
        )


async def _rotate(
    session: AsyncSession,
    fabrica: SessionFactory,
    resolver: ProviderResolver,
    actor_id: UUID,
) -> None:
    with unit_of_work(actor_id):
        version = await rotation.rotate_or_resume(fabrica, resolver=resolver)
        typer.echo(f"{COMMAND}: version={version}")
        resultado = await rotation.rewrap_all(fabrica, resolver=resolver, actor=actor_id)
        typer.echo(f"{COMMAND}: total={resultado.total}")
        typer.echo(f"{COMMAND}: hecho={resultado.done}/{resultado.total}")
        if resultado.failed_key_id is not None:
            exit_after_failure(COMMAND, resultado)
        detalle: dict[str, object] = {"event": "rotate_kek", "version": version}
        detalle |= {"total": resultado.total, "done": resultado.done}
        await _auditar(session, actor_id, resultado.job_id, detalle)
    typer.echo(f"{COMMAND}: llaves re-envueltas")


async def _trim(
    session: AsyncSession,
    fabrica: SessionFactory,
    resolver: ProviderResolver,
    actor_id: UUID,
    respaldo_creado: datetime | None,
) -> None:
    version = await rotation.trim_ready_version(fabrica, resolver=resolver)
    if version is None:
        reject(TRIM_NO_LISTO, COMMAND)
    terminado = await rotation.ultimo_rewrap_terminado(fabrica)
    if terminado is None or respaldo_creado is None or respaldo_creado <= terminado:
        reject(SIN_SNAPSHOT_POSTERIOR, COMMAND)
    if (rechazo := confirmation_error("RECORTAR", yes=False)) is not None:
        reject(rechazo, COMMAND)
    with unit_of_work(actor_id):
        try:
            await rotation.trim_kek_checked(fabrica, resolver=resolver, version=version)
        except rotation.TrimNotReady:
            reject(TRIM_CAMBIO, COMMAND)
        detalle: dict[str, object] = {"event": "trim_kek", "min_decryption_version": version}
        await _auditar(session, actor_id, None, detalle)
    typer.echo(f"{COMMAND}: min_decryption_version={version}")


async def _flow(settings: Settings, opciones: RuntimeOptions, p: Pedido) -> None:
    resolver = provider_mod.make_resolver(settings)
    async with cli_runtime(settings, opciones) as session:
        fabrica = db.get_sessionmaker()
        async with session.begin():
            actor_id = await resolve_admin_actor(session, p.actor, required=True)
        try:
            revision = await custody_proofs(
                session, settings, p.manifest, now=current_clock().now_utc()
            )
        except CustodyRejected as error:
            reject(str(error), COMMAND)
        with custody_errors(COMMAND):
            if p.trim:
                await _trim(session, fabrica, resolver, actor_id, revision.created_at)
            else:
                async with rotation.kek_lock(fabrica):
                    await _rotate(session, fabrica, resolver, actor_id)


def register(app: typer.Typer) -> None:
    @app.command("rotate-kek")
    def rotate_kek_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
        trim: Annotated[bool, typer.Option("--trim")] = False,
        manifest: Annotated[Path, typer.Option("--manifest")] = DEFAULT_MANIFEST,
    ) -> None:
        """Rota la KEK de OpenBao y re-envuelve las llaves; con --trim recorta las viejas."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        _run(_flow(settings, opciones, Pedido(actor, trim, manifest)))
