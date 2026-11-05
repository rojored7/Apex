"""`seed-notifications [--as <correo>]` (S5-B6, US-120 y US-121; S5-D25, S5-D97).

Siembra las dos plantillas y las cinco reglas por defecto con `notifications.service.seed_defaults`.
Idempotente (la segunda corrida no crea nada) y auditada a nombre de `--as` o del usuario técnico.
`cli seed` (primer seed) la invoca también dentro de su transacción. Imprime solo dos números:
plantillas y reglas creadas. Con `ENV=production` exige `--as` y rechaza `--db-timeouts off`.
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
from app.core.config import Settings

COMMAND = "seed-notifications"


async def _seed_notifications(
    settings: Settings, options: RuntimeOptions, actor_email: str | None
) -> tuple[int, int]:
    """`(plantillas, reglas)` creadas; sale con 2 (por `resolve_actor`) si `--as` no sirve."""
    from app.modules.notifications.service import seed_defaults

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            async with session.begin():
                resultado = await seed_defaults(session)
    return resultado.templates_created, resultado.rules_created


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def seed_notifications_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Crea las plantillas y reglas de aviso por defecto (idempotente)."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        plantillas, reglas = _run(_seed_notifications(settings, opciones, actor))
        typer.echo(f"{COMMAND}: plantillas creadas {plantillas}, reglas creadas {reglas}")
