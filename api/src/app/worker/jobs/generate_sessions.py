"""Job diario `generate_sessions`: crea las sesiones de los próximos 14 días (S7-B1, US-156;
S7-D10).

`run(ctx)` llama `classes.service.generate_sessions(session, today=ctx.today)` en una sola
transacción y devuelve `JobResult(ok=True, details={"creadas": N, "franjas": M})`: solo enteros de
`DETAIL_KEYS`. El actor (`SYSTEM_USER_ID`, N-15), el reclamo de `job_runs`, el tiempo máximo y el
cierre los pone el runner. Re-ejecutable el mismo día: lo que ya existe no se vuelve a crear. Se
registra después de `expirations` y antes de `notify` para que `sign_audit` firme las filas nuevas
el mismo día. Sin datos personales en el log ni en `details`.
"""

from __future__ import annotations

from typing import Final

from app.modules.classes import service as classes_service
from app.worker.runner import JobContext, JobResult

NAME: Final = "generate_sessions"


async def run(ctx: JobContext) -> JobResult:
    """Genera las sesiones que faltan desde `ctx.today` (docstring del módulo)."""
    async with ctx.session_factory() as session:
        resultado = await classes_service.generate_sessions(session, today=ctx.today)
        await session.commit()
    return JobResult(ok=True, details={"creadas": resultado.created, "franjas": resultado.slots})
