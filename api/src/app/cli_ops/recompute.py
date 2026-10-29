"""`recompute-memberships` (S4A-B2, US-094): implementación asíncrona y guardas.

Extraído de `cli.py` en B0 (S4B-D28) sin cambios de comportamiento; el comando Typer sigue en
`cli.py`. Solo importa `cli_base`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Final

from app.cli_base import (
    RuntimeOptions,
    cli_runtime,
    production_guard_error,
    reject,
    resolve_actor,
    unit_of_work,
)
from app.core.config import Settings

RECOMPUTE_KEYS: Final = (
    "revisados",
    "cambiadas",
    "por_vencer",
    "vencidas",
    "otras",
    "busy_omitidos",
    "errores",
)
"""Los conteos de `RecomputeSummary` que imprime `recompute-memberships`, en orden."""
EXIT_BY_SIMULATED_RESULT: Final = {"ok": 0, "error": 1, "running": 3}
SIMULATE_WITH_AS_REJECTED: Final = (
    "--simulate no admite --as: la corrida simulada se atribuye al usuario técnico"
)
"""S4A-D89 (revisión de seguridad de B2, L-1): el runner fija `SYSTEM_USER_ID`; aceptar `--as`
dejaría creer que la auditoría simulada va a nombre de esa persona."""


def _recompute_target(
    settings: Settings,
    opciones: RuntimeOptions,
    on_date: str | None,
    *,
    simulate: bool,
    actor: str | None,
) -> date:
    """El día del recálculo, o salida 2: fecha inválida, `--simulate` con `--as` (S4A-D89),
    producción sin `--as` o con `--db-timeouts off` (S4A-D53), o la guarda de `--date` y
    `--simulate` (S4A-D48, E5)."""
    from app.core.clock import current_clock
    from app.worker.runtime import clock_override_error, simulation_error

    try:
        pedido = date.fromisoformat(on_date) if on_date is not None else None
    except ValueError:
        reject("--date inválida (use AAAA-MM-DD)", "recompute-memberships")
    if simulate and actor is not None:
        reject(SIMULATE_WITH_AS_REJECTED, "recompute-memberships")
    if (rechazo_prod := production_guard_error(settings, opciones, actor)) is not None:
        reject(rechazo_prod, "recompute-memberships")
    hoy = current_clock().today_bogota()
    objetivo = pedido or hoy
    rechazo = clock_override_error(objetivo, hoy, simulate=simulate, settings=settings)
    if rechazo is None and simulate:
        rechazo = simulation_error(settings)
    if rechazo is not None:
        reject(rechazo, "recompute-memberships")
    return objetivo


async def _recompute(
    settings: Settings,
    options: RuntimeOptions,
    objetivo: date,
    simulate: bool,
    actor_email: str | None,
) -> tuple[dict[str, Any], int]:
    """`(conteos, código de salida)`; sale con 2 (por `resolve_actor`) si `--as` no sirve."""
    from app.core import db
    from app.modules.memberships.service import recompute_statuses

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        if simulate:
            return await _recompute_simulated(db.get_sessionmaker(), objetivo)
        # El actor debe seguir fijado durante cada commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            resumen = await recompute_statuses(db.get_sessionmaker(), today=objetivo)
    conteos = asdict(resumen)
    return conteos, 1 if resumen.busy_omitidos + resumen.errores else 0


async def _recompute_simulated(session_factory: Any, objetivo: date) -> tuple[dict[str, Any], int]:
    """La corrida simulada por el runner del worker (S4A-D89): reclama `expirations_sim` con el
    reloj a las 12:00 de Bogotá de `objetivo`; nunca la fila real del día."""
    from zoneinfo import ZoneInfo

    from app.core.clock import FrozenClock
    from app.worker.registry import get_registry
    from app.worker.runner import run_job
    from app.worker.schedule import WORKER_TIMEZONE

    spec = next(s for s in get_registry() if s.name == "expirations")
    zona = ZoneInfo(WORKER_TIMEZONE)
    reloj = FrozenClock(datetime(objetivo.year, objetivo.month, objetivo.day, 12, tzinfo=zona))
    salida = await run_job(spec, clock=reloj, session_factory=session_factory, simulated=True)
    return dict(salida.details), EXIT_BY_SIMULATED_RESULT.get(salida.result, 1)
