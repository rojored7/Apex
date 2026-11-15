"""`seed-benchmarks [--as <correo>]` (S8-A2, US-166, N-46; S8-D6, S5-D97).

Siembra los doce benchmarks clásicos con `wods.service.seed_benchmarks`. Idempotente (la segunda
corrida no crea nada, no pisa ediciones) y auditada a nombre de `--as` o del usuario técnico
(N-15), en UNA transacción. Imprime solo el número de benchmarks creados. Con `ENV=production`
exige `--as` de un admin activo (S7-D37) y rechaza `--db-timeouts off`.
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
    resolve_admin_actor,
    runtime_options,
    unit_of_work,
)
from app.core.config import Settings

COMMAND = "seed-benchmarks"


async def _seed_benchmarks(
    settings: Settings, options: RuntimeOptions, actor_email: str | None
) -> int:
    """Benchmarks creados; sale con 2 (por `resolve_*_actor`) si `--as` no sirve."""
    from app.modules.wods.service import seed_benchmarks

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            if settings.ENV == "production":
                actor = await resolve_admin_actor(session, actor_email)
            else:
                actor = await resolve_actor(session, actor_email)
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en la sesión.
        with unit_of_work(actor):
            async with session.begin():
                return await seed_benchmarks(session)


def register(app: typer.Typer) -> None:
    @app.command(COMMAND)
    def seed_benchmarks_command(
        ctx: typer.Context,
        actor: Annotated[str | None, typer.Option("--as")] = None,
    ) -> None:
        """Crea los benchmarks clásicos que falten (idempotente)."""
        settings = cli_base.get_settings()
        opciones = runtime_options(ctx)
        if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
            reject(rechazo, COMMAND)
        creados = _run(_seed_benchmarks(settings, opciones, actor))
        typer.echo(f"{COMMAND}: benchmarks creados {creados}")
