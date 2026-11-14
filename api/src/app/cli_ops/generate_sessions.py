"""`generate-sessions [--days 14] [--as <correo>]` (S7-B1, US-156; S7-D10).

Genera a mano las sesiones de los próximos `--days` días (1 a 28, 14 por omisión) desde las franjas
activas, con `classes.service.generate_sessions` y el mismo candado asesor (`4_270_006`) que el job:
si corren a la vez, una sola inserta. Idempotente (lo que ya existe, también las canceladas, no se
vuelve a crear) y auditada a nombre de `--as` (admin activo) o del usuario técnico. No escribe
`worker.job_runs`. Imprime solo conteos. Con `ENV=production` exige `--as` y rechaza
`--db-timeouts off`. Salida 2 por uso (`--days` fuera de rango, `--as` inexistente).
"""

from __future__ import annotations

from typing import Annotated

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
    unit_of_work,
)
from app.core.clock import current_clock
from app.core.config import Settings

COMMAND = "generate-sessions"
DAYS_DEFAULT = 14
DAYS_MIN = 1
DAYS_MAX = 28


async def _generate(
    settings: Settings, options: RuntimeOptions, days: int, actor_email: str | None
) -> tuple[int, int]:
    """`(creadas, franjas activas)`; sale con 2 si `--as` no es un admin activo."""
    from app.modules.classes import service

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, actor_email, required=False)
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            async with session.begin():
                resultado = await service.generate_sessions(
                    session, today=current_clock().today_bogota(), days=days
                )
    return resultado.created, resultado.slots


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def generate_sessions_command(
        ctx: typer.Context,
        days: Annotated[int, typer.Option("--days", min=DAYS_MIN, max=DAYS_MAX)] = DAYS_DEFAULT,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Genera las sesiones de los próximos días desde las franjas activas (idempotente)."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        creadas, franjas = _run(_generate(settings, opciones, days, actor))
        typer.echo(f"{COMMAND}: creadas {creadas}, franjas {franjas}")
