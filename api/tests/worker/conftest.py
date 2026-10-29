"""Kit de pruebas del worker (plan del Sprint 4A, sección 2, bloque B1; S4A-D3, S4A-D55, S4A-D56).

- `session_factory`: `async_sessionmaker` sobre el `engine` de la prueba, con commit real (el
  worker abre sesiones cortas propias). Al salir borra lo que quedó como `dos_sesiones`
  (`limpiar_tras_dos_sesiones`: planes, `worker.job_runs` y la cola de `audit.audit_log`).
- `reloj_worker`: `FrozenClock` en `2026-10-21T15:00:00Z` (10:00 de Bogotá, después de las 07:00)
  instalado con `set_clock` y restaurado al salir.
- `spec_que_escribe`: `JobSpec("prueba_escribe")` que da de alta un plan por el service real
  (`plans.service.create`) y anota el actor y el lote que ve dentro del job.
- `spec_que_lanza`: `JobSpec("prueba_lanza")` que da de alta un plan dentro de su transacción y
  lanza `RuntimeError("documento 1020304417 en el mensaje")` antes de confirmar (la escritura se
  revierte; el documento nunca debe llegar al log, a stdout ni a `job_runs`).
- `limpiar_job_runs` (autouse): `LIMPIAR_JOB_RUNS` al terminar cada prueba.
- `latido_tmp`: `HEARTBEAT_PATH` del runtime (y de `main`, si lo copia) apunta a `tmp_path`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.audit import AuditEntry
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.context import current_actor, current_batch
from app.modules.plans import service as plans_service
from app.modules.plans.schemas import PlanCreate
from app.worker import main as worker_main
from app.worker import runtime
from app.worker.registry import JobSpec
from app.worker.runner import JobContext, JobResult
from tests.conftest import LIMPIAR_JOB_RUNS, limpiar_tras_dos_sesiones

T_WORKER = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)
DOCUMENTO = "1020304417"
MENSAJE_CON_DOCUMENTO = f"documento {DOCUMENTO} en el mensaje"
PLAN_DEL_JOB = "Plan del worker"
PLAN_REVERTIDO = "Plan que se revierte"


@dataclass
class SpecObservado:
    """Un `JobSpec` de prueba y lo que vio por dentro cada vez que corrió."""

    spec: JobSpec
    actores: list[UUID | None] = field(default_factory=list)
    lotes: list[UUID | None] = field(default_factory=list)
    contextos: list[JobContext] = field(default_factory=list)


def _cuerpo_plan(nombre: str) -> PlanCreate:
    return PlanCreate(name=nombre, price_cop=120_000, kind="days", duration_days=30)


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with engine.connect() as conexion:
        ultima_seq = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima_seq or 0)


@pytest.fixture
def reloj_worker() -> Iterator[FrozenClock]:
    reloj = FrozenClock(T_WORKER)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


@pytest.fixture
def spec_que_escribe() -> SpecObservado:
    observado = SpecObservado(spec=None)  # type: ignore[arg-type]

    async def correr(ctx: JobContext) -> JobResult:
        observado.actores.append(current_actor.get())
        observado.lotes.append(current_batch.get())
        observado.contextos.append(ctx)
        async with ctx.session_factory() as sesion, sesion.begin():
            await plans_service.create(sesion, _cuerpo_plan(PLAN_DEL_JOB))
        return JobResult(ok=True, details={"revisados": 1})

    observado.spec = JobSpec(name="prueba_escribe", run=correr, hour=7, minute=0, timeout_s=900)
    return observado


@pytest.fixture
def spec_que_lanza() -> SpecObservado:
    observado = SpecObservado(spec=None)  # type: ignore[arg-type]

    async def correr(ctx: JobContext) -> JobResult:
        observado.actores.append(current_actor.get())
        async with ctx.session_factory() as sesion, sesion.begin():
            await plans_service.create(sesion, _cuerpo_plan(PLAN_REVERTIDO))
            raise RuntimeError(MENSAJE_CON_DOCUMENTO)

    observado.spec = JobSpec(name="prueba_lanza", run=correr, hour=7, minute=0, timeout_s=900)
    return observado


@pytest.fixture(autouse=True)
async def limpiar_job_runs(migrated_database: str) -> AsyncIterator[None]:
    try:
        yield
    finally:
        motor = create_async_engine(migrated_database, hide_parameters=True)
        try:
            async with motor.begin() as conexion:
                await conexion.execute(text(LIMPIAR_JOB_RUNS))
        finally:
            await motor.dispose()


@pytest.fixture
def latido_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ruta = tmp_path / "apex-worker-heartbeat"
    monkeypatch.setattr(runtime, "HEARTBEAT_PATH", ruta)
    if hasattr(worker_main, "HEARTBEAT_PATH"):
        monkeypatch.setattr(worker_main, "HEARTBEAT_PATH", ruta)
    return ruta
