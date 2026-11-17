"""`derive-records [--as <correo>] [--dry-run]` (S9-B6; S9-D21, S9-D42, S9-D62, M-6).

Deriva los récords de los resultados anteriores a v0.6 (y repara los que un fallo blando dejó sin
derivar). Por socio vivo (lotes de 200 por id): UNA transacción, `lock_member` primero y
`athletes.service.rederive_member(strict=True)`, que recorre TODAS sus marcas (sin topes).
Idempotente, auditado (un `insert` por récord y una fila resumen solo con conteos), sin
`PersonalRecordSet`. Puede crear históricos; el vigente de cada objetivo queda en el máximo real.

«Base ocupada» revierte, espera `BUSY_WAIT_S` y reintenta `BUSY_ATTEMPTS` veces y, si sigue, cuenta
en `ocupados`; otro error revierte ese socio y cuenta en `fallidos` (al log solo el tipo). Con
ocupados o fallidos sale con 1. `--dry-run` revierte cada socio: informa sin escribir. Un fallo de
conexión aborta, pero antes imprime los conteos parciales. Con `ENV=production` exige `--as` de un
admin activo y rechaza `--db-timeouts off`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Annotated, Final
from uuid import UUID

import typer
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    cli_runtime,
    production_guard_error,
    reject,
    resolve_actor,
    resolve_admin_actor,
    runtime_options,
    unit_of_work,
)
from app.core import audit
from app.core.config import Settings
from app.core.db import DatabaseBusy, is_connection_error, translate_busy
from app.core.locks import lock_member

COMMAND = "derive-records"
BATCH_SIZE: Final = 200
BUSY_ATTEMPTS: Final = 3
BUSY_WAIT_S: float = 1.0
AUDIT_TABLE: Final = "athletes.personal_records"
logger = logging.getLogger("app.athletes")


@dataclass(slots=True)
class Summary:
    socios: int = 0
    creados: int = 0
    ocupados: int = 0
    fallidos: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.ocupados or self.fallidos else 0

    def line(self, dry_run: bool) -> str:
        c = asdict(self)
        texto = ", ".join(f"{clave} {valor}" for clave, valor in c.items())
        return f"{COMMAND}: {texto}" + (" (simulacro: no se escribió nada)" if dry_run else "")


def _is_busy(error: BaseException) -> bool:
    if isinstance(error, DatabaseBusy):
        return True
    return isinstance(error, DBAPIError) and translate_busy(error) is not None


async def _one_member(
    session: AsyncSession, member_id: UUID, *, dry_run: bool, summary: Summary
) -> None:
    """Una transacción por socio, con reintento de «base ocupada»; actualiza `summary`."""
    from app.modules.athletes import service as athletes_service

    for intento in range(1, BUSY_ATTEMPTS + 1):
        transaccion = await session.begin()
        try:
            await lock_member(session, member_id)
            resultado = await athletes_service.rederive_member(session, member_id, strict=True)
            if dry_run:
                await transaccion.rollback()
            else:
                await transaccion.commit()
        except Exception as error:
            await session.rollback()
            if is_connection_error(error):
                raise
            if _is_busy(error):
                if intento < BUSY_ATTEMPTS:
                    await asyncio.sleep(BUSY_WAIT_S)
                    continue
                summary.ocupados += 1
                return
            summary.fallidos += 1
            logger.warning(
                "derive-records: socio fallido", extra={"error_type": type(error).__name__}
            )
            return
        summary.creados += resultado.created
        return


async def _derive(
    settings: Settings,
    options: RuntimeOptions,
    actor_email: str | None,
    dry_run: bool,
    summary: Summary,
) -> None:
    from app.modules.members import service as members_service
    from app.modules.results import service as results_service

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            if settings.ENV == "production":
                actor = await resolve_admin_actor(session, actor_email)
            else:
                actor = await resolve_actor(session, actor_email)
        # El actor debe seguir fijado durante cada commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            despues: UUID | None = None
            while True:
                async with session.begin():
                    ids = await results_service.member_ids_with_marks(
                        session, after=despues, limit=BATCH_SIZE
                    )
                    vivos = await members_service.live_ids_among(session, ids)  # sin bajas (S9-D62)
                if not ids:
                    break
                for member_id in (i for i in ids if i in vivos):
                    summary.socios += 1
                    await _one_member(session, member_id, dry_run=dry_run, summary=summary)
                despues = ids[-1]
            if not dry_run:
                async with session.begin():
                    await audit.record(
                        session,
                        action="insert",
                        table_name=AUDIT_TABLE,
                        record_id=None,
                        before=None,
                        after={COMMAND: asdict(summary)},
                        user_id=actor,
                    )


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def derive_records_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    ) -> None:
        """Deriva los récords de los resultados anteriores a v0.6 (idempotente)."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        resumen = Summary()
        try:
            _run(_derive(settings, opciones, actor, dry_run, resumen))
        except typer.Exit:
            raise
        except Exception:
            typer.echo(resumen.line(dry_run), err=False)  # conteos parciales antes de abortar
            raise
        typer.echo(resumen.line(dry_run))
        if resumen.exit_code:
            typer.echo(
                f"{COMMAND}: quedaron socios ocupados o fallidos; repita el comando", err=True
            )
        raise typer.Exit(code=resumen.exit_code)
