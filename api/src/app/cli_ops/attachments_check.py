"""`attachments-check [--as <correo>]` (S6-C1, US-147; S6-D22, S6-D76, S6-D80).

Solo lectura: compara las filas de `attachments.attachments` con los objetos del almacenamiento
(`attachments.service.orphan_report`). Sale 0 sin huérfanos y 1 con ellos. La salida trae los dos
conteos y debajo la lista: los IDS de las filas sin objeto y los NOMBRES hexadecimales de los
objetos sin fila; nunca el `filename_random` de una fila (con S3 es la clave del objeto). No borra
nada: reparar es decisión de la persona (procedimiento manual en `docs/operacion/adjuntos.md`).
Con `ENV=production` exige `--as` (un admin activo); un correo desconocido sale 2.
"""

from __future__ import annotations

from typing import Annotated, Final

import typer

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    cli_runtime,
    production_guard_error,
    reject,
    resolve_admin_actor,
    runtime_options,
)
from app.core.config import Settings

COMMAND: Final = "attachments-check"


async def _check(settings: Settings, options: RuntimeOptions, actor_email: str | None) -> int:
    from app.modules.attachments import service

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            await resolve_admin_actor(session, actor_email, required=False)
            informe = await service.orphan_report(session)
    typer.echo(f"{COMMAND}: filas sin objeto: {len(informe.rows_without_object)}")
    typer.echo(f"{COMMAND}: objetos sin fila: {len(informe.objects_without_row)}")
    for id_ in informe.rows_without_object:
        typer.echo(f"  fila sin objeto: {id_}")
    for nombre in informe.objects_without_row:
        typer.echo(f"  objeto sin fila: {nombre}")
    return 1 if informe.rows_without_object or informe.objects_without_row else 0


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def attachments_check_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Lista filas sin objeto y objetos sin fila (solo lectura)."""
        settings, opciones = cli_base.get_settings(), runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        if codigo := _run(_check(settings, opciones, actor)):
            raise typer.Exit(code=codigo)
