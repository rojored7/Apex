"""Fábrica de `worker.job_runs` (plan del Sprint 4A, sección 2, bloque B1; S4A-D3, S4A-D38).

`make_job_run(session, job_name, run_date, ...)` inserta una corrida con Core (sin pasar por
`claim_run`) y confirma, como `make_plan`. Por defecto la fila queda `ok` con `started_at` en el
instante del reloj actual y `finished_at` igual. La tabla no tiene columnas cifradas
(`test_no_plaintext_at_rest.py` no la exige) ni auditoría (S4A-D3).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID
from app.core.jobs import JobRun, JobRunView


async def make_job_run(
    session: AsyncSession,
    job_name: str,
    run_date: date,
    *,
    result: str = "ok",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
    created_by: UUID = SYSTEM_USER_ID,
) -> JobRunView:
    """Inserta la corrida y confirma; una `running` queda sin `finished_at` salvo que se pida."""
    inicio = started_at or current_clock().now_utc()
    fin = finished_at if finished_at is not None or result == "running" else inicio
    valores: dict[str, Any] = {
        "id": uuid4(),
        "job_name": job_name,
        "run_date": run_date,
        "started_at": inicio,
        "finished_at": fin,
        "result": result,
        "error": error,
        "details": details or {},
        "created_by": created_by,
    }
    await session.execute(insert(JobRun).values(**valores))
    await session.commit()
    return JobRunView(
        id=valores["id"],
        job_name=job_name,
        run_date=run_date,
        started_at=inicio,
        finished_at=fin,
        result=result,
        error=error,
        details=valores["details"],
    )
