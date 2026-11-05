"""`notify --generate-only [--as <correo>]` (S5-B7, US-124; S5-D26, S5-D97). Provisional.

B7 expone la generación del día; B8 completa el comando con `--send-only` y el reclamo
`claim_run`. Con `--generate-only` llama `notifications.service.generate_today` con el "hoy" de
Bogotá del reloj (el cruce de medianoche UTC no cambia el día) y confirma por lote. Imprime
`notify: generados N, ya renovaron N, sin consentimiento N, sin reglas sí|no`. Sin
`--generate-only` sale con 2. Con `ENV=production` exige `--as` y rechaza `--db-timeouts off`.
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
    resolve_actor,
    runtime_options,
    unit_of_work,
)
from app.core.clock import current_clock
from app.core.config import Settings

COMMAND = "notify"


async def _generate(settings: Settings, options: RuntimeOptions, actor_email: str | None) -> str:
    from app.modules.notifications import service

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        with unit_of_work(actor):
            resultado = await service.generate_today(session, current_clock().today_bogota())
            await session.commit()
    return (
        f"{COMMAND}: generados {resultado.generados}, ya renovaron {resultado.ya_renovaron}, "
        f"sin consentimiento {resultado.sin_consentimiento}, "
        f"sin reglas {'sí' if resultado.sin_reglas else 'no'}"
    )


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def notify_command(
        ctx: typer.Context,
        generate_only: Annotated[bool, typer.Option("--generate-only")] = False,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Genera los avisos del día (idempotente). B8 suma `--send-only` y el envío."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        if not generate_only:
            reject("por ahora solo existe --generate-only", COMMAND)
        typer.echo(_run(_generate(settings, opciones, actor)))
