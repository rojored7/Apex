"""`seed --demo` (S4B-B1, US-111; S4B-D32, D65): guardas y salida; la siembra vive en `app.seed`.

Con `ENV=production` exige `--as` (un admin activo), `--allow-production` y que
`current_database()` termine en `_demo`, `_ensayo` o `_smoke` (consulta constante); si no, sale
con 2 sin escribir. No lee `.env.seed` ni pide `ADMIN_*`. Imprime solo conteos.
"""

from __future__ import annotations

from typing import Any, Final

import typer

from app import cli_base
from app.cli_base import (
    RuntimeOptions,
    _run,
    cli_runtime,
    crypto_runtime,
    production_guard_error,
    reject,
    resolve_admin_actor,
    runtime_options,
)
from app.core.clock import current_clock
from app.core.config import Settings
from app.seed.apply import NonDemoDataError, apply_demo

CURRENT_DATABASE_SQL: Final = "SELECT current_database()"
"""Consulta constante de la guarda de producción; las pruebas la reemplazan por otra constante
(`SELECT 'apex_demo'`) en lugar de crear bases (S4B-D65)."""
SAFE_DATABASE_SUFFIXES: Final = ("_demo", "_ensayo", "_smoke")
UNSAFE_DATABASE_MESSAGE: Final = (
    "con ENV=production la demostración solo corre en una base cuyo nombre termina en "
    + ", ".join(SAFE_DATABASE_SUFFIXES)
)
NON_DEMO_MESSAGE: Final = (
    "la base ya tiene socios que no son de demostración; use --force-demo-on-non-empty"
)
STEP_FAILED_MESSAGE: Final = (
    "un paso falló; repita el comando para reanudar (no queda nada a medias)"
)


async def _check_database_name(session: Any) -> None:
    """S4B-D65: nunca siembra en producción sobre una base cuyo nombre no sea de ensayo."""
    conexion = await session.connection()
    resultado = await conexion.exec_driver_sql(CURRENT_DATABASE_SQL)
    nombre = str(resultado.scalar_one())
    if not nombre.endswith(SAFE_DATABASE_SUFFIXES):
        reject(UNSAFE_DATABASE_MESSAGE, "seed")


async def _seed_demo(
    settings: Settings, options: RuntimeOptions, actor: str | None, force: bool
) -> str:
    if settings.ENV == "production":  # M-7: ANTES de cargar o crear llaves
        async with cli_runtime(settings, options) as sesion:
            async with sesion.begin():
                await _check_database_name(sesion)
    async with crypto_runtime(settings, options) as session:
        async with session.begin():
            actor_id = await resolve_admin_actor(session, actor, required=False)
        try:
            hoy = current_clock().today_bogota()
            res = await apply_demo(settings, actor_id, hoy, force_on_non_empty=force)
        except NonDemoDataError:
            reject(NON_DEMO_MESSAGE, "seed")
        except typer.Exit:
            raise
        except Exception:
            reject_failure()
    if res.already_applied:
        return "seed de demo ya aplicado"
    return (
        f"seed de demo: planes={res.plans} socios={res.members} "
        f"membresias={res.memberships} pagos={res.payments}"
    )


def reject_failure() -> None:
    """Un paso falló (no se imprime la causa: puede traer datos); salida 1."""
    typer.echo(f"seed: {STEP_FAILED_MESSAGE}", err=True)
    raise typer.Exit(code=1)


def run_seed_demo(
    ctx: typer.Context, actor: str | None, force: bool, allow_production: bool
) -> None:
    settings = cli_base.get_settings()  # por el módulo: las pruebas lo reemplazan (S4B-D29)
    opciones = runtime_options(ctx)
    if (rechazo := production_guard_error(settings, opciones, actor)) is not None:
        reject(rechazo, "seed")
    if settings.ENV == "production" and not allow_production:
        reject("--allow-production es obligatorio con ENV=production", "seed")
    typer.echo(_run(_seed_demo(settings, opciones, actor, force)))
