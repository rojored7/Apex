"""`retire-key <key_id> --as <correo> --confirm-audit-blobs N [--manifest RUTA]` (S4B-B3b).

`retired` es irreversible (S4B-D38, D63, D86). Antes de cambiar nada exige, en este orden:
- un `verify-kek-backup` `ok` de una persona de menos de 24 h (`crypto_ops`);
- un `latest.json` con su `.minisig` al lado (solo existencia; la firma no se verifica desde
  `tools`: la imagen del api no trae `minisign`, S4B-D149), bajo `BACKUP_DIR` (sin enlaces),
  `verify == "ok"` y menos de 24 h:
  ausente, viejo, ilegible, sin firma o con `verify != ok` dan el mismo texto fijo.
Luego cuenta las filas de negocio con ese `key_id` (deben ser 0) y los blobs de `audit.audit_log`
(que el operador confirma con `N`) e imprime `retire-key: filas_negocio=F` y `retire-key:
audit_blobs=A`; `N` distinto de `A` sale 2. En orden: `retire-key: llave retirada`, auditoría
`update` sobre `crypto.crypto_keys` con `after = {"event": "retire", "business_rows": 0,
"audit_blobs": N}` y `crypto_ops` `rotate`.
Todo rechazo sale con 2 (textos fijos NO_VERIFY y NO_MANIFEST); sin material ni blobs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    crypto_runtime,
    production_guard_error,
    reject,
    resolve_admin_actor,
    runtime_options,
    unit_of_work,
)
from app.core import audit
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto import service

COMMAND = "retire-key"
AUDIT_TABLE = "crypto.crypto_keys"
DEFAULT_MANIFEST = Path("/data/backups/latest.json")
MAX_MANIFEST_BYTES = 1 << 20
MANIFEST_AGE = timedelta(hours=24)
CLOCK_SKEW = timedelta(minutes=5)
NO_VERIFY = "no hay un verify-kek-backup ok de una persona en las últimas 24 h"
NO_MANIFEST = "no hay un latest.json reciente con firma adjunta en /data/backups (verify: ok)"


def _inside(path: Path, base: Path) -> bool:
    """`path` (sin enlaces) resuelto queda bajo `base` resuelto (S4B-D149)."""
    try:
        firma = path.with_name(path.name + ".minisig")
        if path.is_symlink() or firma.is_symlink():
            return False
        return path.resolve().is_relative_to(base.resolve())
    except OSError:
        return False


def manifest_is_fresh(path: Path, now: datetime, base: Path) -> bool:
    """`latest.json` bajo `base`, con `.minisig`, `verify == "ok"` y creado hace menos de 24 h."""
    try:
        firma = path.with_name(path.name + ".minisig")
        if not _inside(path, base) or not (path.is_file() and firma.is_file()):
            return False
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return False
        datos = json.loads(path.read_text(encoding="utf-8"))
        creado = datetime.strptime(datos["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        verificado = datos["verify"] == "ok"
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return verificado and -CLOCK_SKEW <= now - creado < MANIFEST_AGE


async def _require_recent(session: AsyncSession, manifest: Path, base: Path) -> None:
    async with session.begin():
        verificado = await service.recent_kek_verify(session, within=service.KEK_VERIFY_WINDOW)
    if not verificado:
        reject(NO_VERIFY, COMMAND)
    if not manifest_is_fresh(manifest, current_clock().now_utc(), base):
        reject(NO_MANIFEST, COMMAND)


async def _count(session: AsyncSession, key_id: UUID) -> tuple[int, int]:
    async with session.begin():
        try:
            filas = sum((await service.count_rows_by_key(session, key_id)).values())
        except ValueError as error:
            reject(str(error), COMMAND)
        blobs = await service.count_audit_blobs(session, key_id)
    typer.echo(f"{COMMAND}: filas_negocio={filas}" + chr(10) + f"{COMMAND}: audit_blobs={blobs}")
    return filas, blobs


async def _retire(session: AsyncSession, key_id: UUID, confirmed: int, actor_id: UUID) -> None:
    try:
        async with session.begin():
            blobs = await service.retire_key(
                session, key_id, confirmed_audit_blobs=confirmed, actor=actor_id
            )
            detalle = {"event": "retire", "business_rows": 0, "audit_blobs": blobs}
            await audit.record(
                session,
                action="update",
                table_name=AUDIT_TABLE,
                record_id=key_id,
                before=None,
                after=detalle,
                user_id=actor_id,
            )
    except (ValueError, service.InvalidTransition) as error:
        reject(str(error), COMMAND)


async def _retire_flow(
    settings: Settings,
    options: RuntimeOptions,
    key_id: UUID,
    actor: str | None,
    confirmed: int,
    manifest: Path,
) -> None:
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=True)
        await _require_recent(session, manifest, settings.BACKUP_DIR)
        filas, blobs = await _count(session, key_id)
        if filas:
            reject("quedan filas de negocio con esa llave; termine la rotación antes", COMMAND)
        if confirmed != blobs:
            reject("--confirm-audit-blobs no coincide con audit_blobs", COMMAND)
        with unit_of_work(actor_id):
            await _retire(session, key_id, confirmed, actor_id)


def register(app: typer.Typer) -> None:
    @app.command("retire-key")
    def retire_key_command(
        ctx: typer.Context,
        key_id: Annotated[str, typer.Argument(help="Id de la llave `decrypt_only` a retirar.")],
        actor: Annotated[str | None, typer.Option("--as")] = None,
        confirm_audit_blobs: Annotated[
            int | None, typer.Option("--confirm-audit-blobs", help="Blobs de audit_log (N).")
        ] = None,
        manifest: Annotated[Path, typer.Option("--manifest")] = DEFAULT_MANIFEST,
    ) -> None:
        """Retira (irreversible) una llave `decrypt_only` sin filas de negocio."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        try:
            llave = UUID(key_id)
        except ValueError:
            reject("key_id no es un UUID válido", COMMAND)
        if confirm_audit_blobs is None or confirm_audit_blobs < 0:
            reject("--confirm-audit-blobs N es obligatorio (cero o más)", COMMAND)
        _run(_retire_flow(settings, opciones, llave, actor, confirm_audit_blobs, manifest))
        typer.echo(f"{COMMAND}: llave retirada")
