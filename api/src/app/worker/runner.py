"""Ejecución de un job y del ciclo diario (US-113; S4A-D6, S4A-D48, S4A-D55).

`run_job(spec, *, clock, session_factory, simulated=False)`:
1. `actor_scope(SYSTEM_USER_ID)` y `batch_scope(uuid4())` **antes** de `claim_run` (S4A-D55 a);
2. `today = clock.today_bogota()`; `job_name = simulated_name(spec.name)` si `simulated`;
3. `claim_run` en una sesión corta y propia con `stale_after = STALE_FACTOR * spec.timeout_s`; si
   devuelve `None` (otra corrida vigente) no corre nada;
4. el job bajo `asyncio.wait_for(spec.run(ctx), spec.timeout_s)`; una excepción del job no sale
   de `run_job`: se registra solo su tipo (`type(exc).__name__`), nunca su mensaje;
5. `await asyncio.shield(finish_run(...))` en `finally` (otra sesión corta), con
   `details["clock_override"] = True` si `simulated`;
6. si falló, `alert("job_failed", job=..., result="error", error_type=...)`.

`run_cycle(registry, *, clock, session_factory)`: para cada `JobSpec` lee `last_run` y corre solo
los que `should_run` (recuperación al arrancar y disparo de las 07:00); un job que falla no
detiene a los demás. Devuelve los `JobOutcome` de los que corrió.

`JobOutcome.result` es el de la fila (`ok` o `error`), o `running` si otra corrida vigente tenía el
reclamo (la CLI lo traduce a la salida 3). Los logs llevan el nombre del job, el día, el resultado
y el tipo del error; nunca el mensaje de la excepción (puede traer datos de un socio).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.alerts import alert
from app.core.clock import Clock, reset_clock, set_clock
from app.core.context import SYSTEM_USER_ID, actor_scope, batch_scope
from app.core.db import sqlstate_of, translate_busy
from app.core.jobs import (
    CLOCK_OVERRIDE_KEY,
    JobRunView,
    check_details,
    claim_run,
    finish_run,
    last_run,
)
from app.worker.schedule import STALE_FACTOR, WORKER_TIMEZONE, should_run, simulated_name

if TYPE_CHECKING:
    from app.worker.registry import JobSpec

logger = logging.getLogger("app.worker")

RESULT_RUNNING: Final = "running"
"""`JobOutcome.result` cuando el job no se reclamó (otra corrida vigente, día ya cerrado en el
ciclo, o la base no dio el candado); la CLI lo traduce a la salida 3."""
LOST_CLAIM: Final = "lost_claim"
LOST_CLAIM_ERROR: Final = "LostClaim"
"""`error_type` del resultado cuando el cierre encontró la fila reclamada por otro (S4A-D77)."""


@dataclass(frozen=True)
class JobContext:
    """Lo que recibe un job: fábrica de sesiones, el "hoy" de Bogotá, el reloj y si simula."""

    session_factory: async_sessionmaker[AsyncSession]
    today: date
    clock: Clock
    simulated: bool = False


@dataclass(frozen=True)
class JobResult:
    """Lo que devuelve un job: `ok` y conteos (`details`, claves de `DETAIL_KEYS`)."""

    ok: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobOutcome:
    """Resumen de una corrida para el ciclo y la CLI (sin datos personales)."""

    job_name: str
    run_date: date
    result: str
    error_type: str | None
    details: dict[str, Any] = field(default_factory=dict)


async def _reclamar(
    session_factory: async_sessionmaker[AsyncSession],
    job_name: str,
    run_date: date,
    *,
    now: datetime,
    timeout_s: int,
    reclaim_finished: bool,
) -> JobRunView | None:
    """`claim_run` en una sesión corta; `None` también si la base no dio el candado a tiempo
    (`lock_timeout` mientras otro reclamo tenía la fila, S3-D67, S4A-D81)."""
    try:
        async with session_factory() as sesion:
            vista = await claim_run(
                sesion,
                job_name,
                run_date,
                now=now,
                stale_after=timedelta(seconds=STALE_FACTOR * timeout_s),
                reclaim_finished=reclaim_finished,
            )
            await sesion.commit()
    except DBAPIError as error:
        if translate_busy(error) is None:
            raise
        logger.warning("job claim busy", extra={"job": job_name, "sqlstate": sqlstate_of(error)})
        return None
    return vista


async def _cerrar(
    session_factory: async_sessionmaker[AsyncSession],
    reclamo: JobRunView,
    *,
    result: str,
    error: str | None,
    details: dict[str, Any],
) -> bool:
    """Cierra el intento; `False` si la fila ya no era de este intento (S4A-D77)."""
    async with session_factory() as sesion:
        vista = await finish_run(
            sesion,
            reclamo.id,
            claimed_started_at=reclamo.started_at,
            result=result,
            error=error,
            details=details,
        )
        await sesion.commit()
    return vista is not None


async def _ejecutar(spec: JobSpec, ctx: JobContext, reclamo: JobRunView) -> JobOutcome:
    """El job bajo `wait_for`; el cierre corre siempre y blindado (S4A-D55 c)."""
    result, error_type, details = "error", None, {}
    token = set_clock(ctx.clock)
    try:
        respuesta = await asyncio.wait_for(spec.run(ctx), spec.timeout_s)
        check_details(respuesta.details)  # `details` fuera del contrato: el job cuenta como error
        result, details = ("ok" if respuesta.ok else "error"), dict(respuesta.details)
    except Exception as exc:
        error_type = type(exc).__name__
    except BaseException as exc:  # cancelación: se cierra la fila y se propaga
        error_type = type(exc).__name__
        raise
    finally:
        reset_clock(token)
        if ctx.simulated:
            details[CLOCK_OVERRIDE_KEY] = True
        cerrado = await asyncio.shield(
            _cerrar(ctx.session_factory, reclamo, result=result, error=error_type, details=details)
        )
    if not cerrado:
        logger.warning(LOST_CLAIM, extra={"job": reclamo.job_name, "result": result})
        result, error_type = "error", LOST_CLAIM_ERROR
    return JobOutcome(reclamo.job_name, ctx.today, result, error_type, details)


def _informar(outcome: JobOutcome) -> None:
    datos = {
        "job": outcome.job_name,
        "run_date": outcome.run_date.isoformat(),
        "result": outcome.result,
        "error_type": outcome.error_type,
    }
    logger.info("job finished", extra=datos)
    if outcome.result == "error":
        contexto = {k: v for k, v in datos.items() if v is not None}
        alert("job_failed", **contexto)


async def run_job(
    spec: JobSpec,
    *,
    clock: Clock,
    session_factory: async_sessionmaker[AsyncSession],
    simulated: bool = False,
    reclaim_finished: bool = True,
) -> JobOutcome:
    """Corre un job con reclamo, actor del sistema, tiempo máximo y cierre blindado.

    `reclaim_finished=True` (el de `--run-once`) permite repetir un día ya cerrado; el ciclo
    programado pasa `False` (S4A-D79).
    """
    job_name = simulated_name(spec.name) if simulated else spec.name
    today = clock.today_bogota()
    with actor_scope(SYSTEM_USER_ID), batch_scope(uuid4()):
        vista = await _reclamar(
            session_factory,
            job_name,
            today,
            now=clock.now_utc(),
            timeout_s=spec.timeout_s,
            reclaim_finished=reclaim_finished,
        )
        if vista is None:
            logger.info("job not claimed", extra={"job": job_name})
            return JobOutcome(job_name, today, RESULT_RUNNING, None)
        ctx = JobContext(session_factory, today, clock, simulated)
        outcome = await _ejecutar(spec, ctx, vista)
    _informar(outcome)
    return outcome


async def _toca(
    spec: JobSpec, *, clock: Clock, session_factory: async_sessionmaker[AsyncSession]
) -> bool:
    """`should_run` con el último intento del job real y la hora programada de hoy."""
    zona = ZoneInfo(WORKER_TIMEZONE)
    hoy = clock.today_bogota()
    programada = datetime(hoy.year, hoy.month, hoy.day, spec.hour, spec.minute, tzinfo=zona)
    async with session_factory() as sesion:
        previa = await last_run(sesion, spec.name)
    ahora = clock.now_utc().astimezone(zona)
    return should_run(spec.name, hoy, ahora, programada, previa, timeout_s=spec.timeout_s)


async def run_cycle(
    registry: Sequence[JobSpec],
    *,
    clock: Clock,
    session_factory: async_sessionmaker[AsyncSession],
) -> list[JobOutcome]:
    """Corre los jobs del registro que `should_run`; uno que falla no detiene a los demás.

    Nunca repite un día ya cerrado (`reclaim_finished=False`, S4A-D79); un job que otro proceso
    tenía reclamado no cuenta como corrido.
    """
    resultados: list[JobOutcome] = []
    for spec in registry:
        try:
            if not await _toca(spec, clock=clock, session_factory=session_factory):
                continue
            outcome = await run_job(
                spec, clock=clock, session_factory=session_factory, reclaim_finished=False
            )
        except Exception as exc:  # la base falló al reclamar o al cerrar: sigue el siguiente
            logger.error(
                "job cycle failed", extra={"job": spec.name, "error_type": type(exc).__name__}
            )
            alert("job_failed", job=spec.name, result="error", error_type=type(exc).__name__)
            continue
        if outcome.result != RESULT_RUNNING:
            resultados.append(outcome)
    return resultados
