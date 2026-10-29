"""Job diario de vencimientos (S4A-B2, US-094; S4A-D1, S4A-D2; reemplaza el marcador de
S4A-D64).

`run(ctx)` llama `memberships.service.recompute_statuses(ctx.session_factory, today=ctx.today)`
y devuelve `JobResult(ok=summary.busy_omitidos + summary.errores == 0,
details=asdict(summary))`: solo conteos con claves de `DETAIL_KEYS` (E2). El actor
(`SYSTEM_USER_ID`), el lote, el reclamo de `job_runs` (`expirations` o `expirations_sim`) y el
cierre los pone el runner. Re-ejecutable el mismo día: el recálculo es idempotente.
"""

from __future__ import annotations

from dataclasses import asdict

from app.modules.memberships import service as memberships_service
from app.worker.runner import JobContext, JobResult

NAME = "expirations"


async def run(ctx: JobContext) -> JobResult:
    """Recalcula la columna `status` de las membresías para `ctx.today` (docstring del módulo)."""
    summary = await memberships_service.recompute_statuses(ctx.session_factory, today=ctx.today)
    return JobResult(ok=summary.busy_omitidos + summary.errores == 0, details=asdict(summary))
