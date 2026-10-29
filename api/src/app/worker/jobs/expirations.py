"""Job diario de vencimientos: marcador hasta S4A-B2 (S4A-D64, enmienda E1).

No abre sesión de negocio ni toca nada: devuelve `JobResult(ok=True, details={"placeholder_ok":
1})` (claves enteras de `DETAIL_KEYS`). Existe para que W0-2 pueda exigir `--run-once
expirations` con código 0 y una fila en `worker.job_runs` antes de B2, que lo reemplaza por el
recálculo real (`memberships.service`) y cambia su prueba.
"""

from __future__ import annotations

from app.worker.runner import JobContext, JobResult

NAME = "expirations"


async def run(ctx: JobContext) -> JobResult:
    """Marcador hasta S4A-B2: no toca la base."""
    return JobResult(ok=True, details={"placeholder_ok": 1})
