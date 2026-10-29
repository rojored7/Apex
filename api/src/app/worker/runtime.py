"""Arranque del proceso worker (US-113; S4A-D6, S4A-D8, S4A-D48, S4A-D56, enmienda E5).

- `worker_runtime(settings)`: contexto async que repite a propósito las líneas de
  `cli.cli_runtime` (listeners de auditoría, `crypto_ops` y cifrado, `main.load_module_services()`,
  `configure_logging`, `db.configure_engine(create_engine_from(settings))` y `dispose_engine` al
  salir) sin importar `cli`; sin keyring ni JWT. Cede la fábrica de sesiones del engine.
- `wait_for_database(settings, *, sleep, max_wait_s)`: sondea `worker.job_runs` (con Core, sin
  `text()`) hasta que responde; entre intentos espera 1, 2, 4, ... segundos, cada espera con tope
  `max_wait_s`, sin límite de intentos (el contenedor queda `unhealthy` mientras tanto).
- `touch_heartbeat_if_db_ok(session_factory, path)`: `SELECT 1` con `statement_timeout` de 5 s
  en una sesión corta; solo si responde toca `path` y devuelve `True`; si la base falla no toca
  nada, no propaga y devuelve `False` (S4A-D56).
- `clock_override_error(target, today, *, simulate, settings)`: guarda dura de `--date`
  (S4A-D48, E5). `None` si `target == today` o si se cumplen las tres condiciones (`--simulate`,
  `ENV=dev` y el nombre de la base de `DATABASE_URL` termina en `_sim` o es `apex_test`); si no,
  el mensaje de rechazo (salida 2).
- `simulation_error(settings)`: la parte de la guarda que vale para cualquier `--simulate`, también
  con la fecha de hoy (`ENV=dev` y base de simulación).
- `CycleTasks` y `build_scheduler`: lo que `main.serve` programa (ciclo de las 07:00 con
  `coalesce=True` y `max_instances=1`, latido cada `HEARTBEAT_INTERVAL_S`) y la espera acotada a
  `SHUTDOWN_GRACE_S` de las corridas en curso al parar.

Ningún mensaje ni log lleva la URL de la base: solo su nombre (que no es secreto) o el tipo del
error.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import db
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.jobs import JobRun
from app.core.logging import configure_logging
from app.worker.runner import JobOutcome, run_cycle
from app.worker.schedule import DAILY_HOUR, DAILY_MINUTE, WORKER_TIMEZONE

if TYPE_CHECKING:
    from app.worker.registry import JobSpec

logger = logging.getLogger("app.worker")

HEARTBEAT_PATH: Path = Path("/tmp/apex-worker-heartbeat")  # noqa: S108 - tmpfs del contenedor
HEARTBEAT_INTERVAL_S: Final = 30
HEARTBEAT_STATEMENT_TIMEOUT: Final = "5s"
SIMULATION_DATABASE_SUFFIX: Final = "_sim"
SIMULATION_TEST_DATABASE: Final = "apex_test"
FIRST_WAIT_S: Final = 1.0
SHUTDOWN_GRACE_S: Final = 30

Sleep = Callable[[float], Awaitable[None]]


def _install_listeners() -> None:
    """Las mismas líneas de `cli.cli_runtime` (S4A-D6): auditoría, `crypto_ops` y cifrado, y los
    services de los módulos (sus suscriptores del bus y los puertos como el gate de pagos)."""
    from app import main as app_main
    from app.core.audit import install_audit_listeners
    from app.core.crypto.oplog import install_oplog_listeners
    from app.core.crypto.types import install_crypto_type_listeners

    install_audit_listeners()
    install_oplog_listeners()
    install_crypto_type_listeners()
    app_main.load_module_services()


@asynccontextmanager
async def worker_runtime(
    settings: Settings,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Preámbulo del worker; cede la fábrica de sesiones y libera el engine al salir."""
    _install_listeners()
    configure_logging(settings)
    db.configure_engine(db.create_engine_from(settings))
    try:
        yield db.get_sessionmaker()
    finally:
        await db.dispose_engine()


async def _probe(settings: Settings) -> None:
    """`SELECT 1 FROM worker.job_runs LIMIT 0` con un engine propio (Core, sin `text()`)."""
    motor = db.create_engine_from(settings)
    try:
        async with motor.connect() as conexion:
            await conexion.execute(select(literal(1)).select_from(JobRun).limit(0))
    finally:
        await motor.dispose()


async def wait_for_database(
    settings: Settings, *, sleep: Sleep = asyncio.sleep, max_wait_s: float = 60
) -> None:
    """Espera a que `worker.job_runs` responda (1, 2, 4, ... s; cada espera con tope)."""
    espera = FIRST_WAIT_S
    while True:
        try:
            await _probe(settings)
        except Exception as error:
            pausa = min(espera, max_wait_s)
            logger.warning(
                "database not ready",
                extra={"error_type": type(error).__name__, "retry_in_s": pausa},
            )
            await sleep(pausa)
            espera = min(espera * 2, max_wait_s)
            continue
        return


async def touch_heartbeat_if_db_ok(
    session_factory: async_sessionmaker[AsyncSession], path: Path
) -> bool:
    """Toca `path` solo si `SELECT 1` responde; nunca propaga un error de la base."""
    try:
        async with session_factory() as sesion, sesion.begin():
            await sesion.execute(
                select(func.set_config("statement_timeout", HEARTBEAT_STATEMENT_TIMEOUT, True))
            )
            await sesion.execute(select(literal(1)))
        await asyncio.to_thread(path.touch)
    except Exception as error:
        logger.warning("heartbeat skipped", extra={"error_type": type(error).__name__})
        return False
    return True


class CycleTasks:
    """Corridas del ciclo diario de `serve` (S4A-D6): el scheduler las lanza blindadas (si
    APScheduler cancela su envoltura al pararse, la corrida sigue) y la parada las espera.

    Un solo `asyncio.Lock` serializa la recuperación del arranque y el disparo de las 07:00
    (S4A-D79): el segundo lee `last_run` cuando el primero ya cerró y no repite el día. Un fallo
    inesperado del ciclo se registra solo con su tipo (`worker cycle failed`, S4A-D84) y no sube
    a APScheduler, cuyo log incluiría el mensaje y la traza."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: Callable[[], Sequence[JobSpec]],
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._lock = asyncio.Lock()
        self._running: set[asyncio.Task[list[JobOutcome]]] = set()

    async def _locked_cycle(self) -> list[JobOutcome]:
        async with self._lock:
            return await run_cycle(
                self._registry(), clock=current_clock(), session_factory=self._session_factory
            )

    async def cycle(self) -> None:
        """`run_cycle` con el reloj del contexto: solo corre lo que `should_run`."""
        tarea = asyncio.create_task(self._locked_cycle())
        self._running.add(tarea)
        tarea.add_done_callback(self._running.discard)
        try:
            await asyncio.shield(tarea)
        except Exception as error:
            logger.error("worker cycle failed", extra={"error_type": type(error).__name__})

    async def heartbeat(self) -> None:
        # `HEARTBEAT_PATH` se lee en cada latido (las pruebas lo redirigen).
        await touch_heartbeat_if_db_ok(self._session_factory, HEARTBEAT_PATH)

    async def wait_running(self) -> None:
        """Espera acotada a `SHUTDOWN_GRACE_S`; lo que siga corriendo se cancela y el runner
        cierra su fila en `error` (`finish_run` bajo `shield`)."""
        if not self._running:
            return
        _, pendientes = await asyncio.wait(set(self._running), timeout=SHUTDOWN_GRACE_S)
        for tarea in pendientes:
            tarea.cancel()
        await asyncio.gather(*pendientes, return_exceptions=True)


def build_scheduler(tasks: CycleTasks) -> AsyncIOScheduler:
    """07:00 de Bogotá y latido cada `HEARTBEAT_INTERVAL_S`, sin solapes ni ráfagas."""
    scheduler = AsyncIOScheduler(timezone=WORKER_TIMEZONE)
    scheduler.add_job(
        tasks.cycle,
        CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE, timezone=WORKER_TIMEZONE),
        id="daily_cycle",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        tasks.heartbeat,
        IntervalTrigger(seconds=HEARTBEAT_INTERVAL_S),
        id="heartbeat",
        coalesce=True,
        max_instances=1,
    )
    return scheduler


def _database_name(settings: Settings) -> str:
    return urlsplit(settings.DATABASE_URL.get_secret_value()).path.lstrip("/")


def simulation_error(settings: Settings) -> str | None:
    """Rechazo de cualquier `--simulate`: exige `ENV=dev` y una base de simulación (E5)."""
    if settings.ENV != "dev":
        return "--simulate solo se acepta con ENV=dev"
    nombre = _database_name(settings)
    if nombre == SIMULATION_TEST_DATABASE or (
        nombre.endswith(SIMULATION_DATABASE_SUFFIX)
        and len(nombre) > len(SIMULATION_DATABASE_SUFFIX)
    ):
        return None
    return (
        f"--simulate exige una base de simulación (nombre terminado en "
        f"{SIMULATION_DATABASE_SUFFIX} o {SIMULATION_TEST_DATABASE}); la actual es {nombre!r}"
    )


def clock_override_error(
    target: date, today: date, *, simulate: bool, settings: Settings
) -> str | None:
    """Mensaje de rechazo de `--date`, o `None` si se acepta (S4A-D48, E5)."""
    if target == today:
        return None
    if not simulate:
        return "--date distinta de hoy exige --simulate (y ENV=dev y una base de simulación)"
    return simulation_error(settings)
