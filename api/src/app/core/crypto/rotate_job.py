"""Rotación de llaves fuera del request y compartida con el CLI (S6-R1, US-145; S6-D43, S6-D61).

Un solo bucle para `rotate-key` (CLI, rol propietario) y para `POST /crypto/keys/{id}/rotate`
(tarea del api, con los grants acotados de la migración 0024):

- `execute_rotation` toma el candado `apex:rotate:<clase>` en una conexión de `rotation_engine(...)`
  (motor propio de una sola conexión: no quita conexiones al pool del api), recarga el keyring,
  recifra de a `batch_size` con `service.reencrypt_batch` (una transacción corta por lote, sesión
  nueva de la fábrica) y cierra con `service.finish_rotation`. Lanza `RotationFailed(code)` (el job
  queda `failed` con un código, nunca texto) o `RotationBusy` (candado ajeno o base ocupada tras
  los reintentos: el job queda como estaba).
- `run_rotation` es la misma rotación para quien no tiene a quién avisar (la tarea del api, el
  arranque): anota el fallo en el log y no relanza.
- `resume_running_jobs` termina, de a uno, los jobs `running` que dejó un reinicio, si el keyring
  está cargado; si no, lo anota y no toca nada (S6-E7).
- Un solo rotador en vuelo por proceso (`ROTATION_SLOTS`): el router reserva el cupo con
  `try_claim_slot` antes de escribir y `launch` lo libera cuando la tarea termina o se cancela.

Sin `core/audit` ni `app.modules`; el tiempo sale de `current_clock()`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Final
from uuid import UUID

from sqlalchemy import URL, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.datastructures import State

from app.core.clock import current_clock
from app.core.config import Settings, get_settings
from app.core.context import actor_scope, current_actor
from app.core.crypto import oplog, recovery, service
from app.core.crypto.keyring import current_keyring
from app.core.crypto.models import CryptoJob
from app.core.crypto.reencryptor import get_reencryptor
from app.core.db import CONNECT_TIMEOUT_S, DatabaseBusy, server_settings_from

logger = logging.getLogger("app.crypto.rotate_job")

ROTATION_SLOTS: Final = 1
ROTATION_MAX_S: Final = 3600
BATCH_ROWS: Final = 500
BATCH_FILES: Final = 10  # S6-D116: igual a `attachments.reencrypt.BATCH_SIZE` (S6-D111)
RETRIES: Final = 3
WAIT_S: Final = 1
EMPTY_PASSES: Final = 5
OPEN_STATES: Final = ("pending", "running")

_slots_used = 0


class RotationFailed(Exception):
    """El job quedó `failed`; `code` es el código guardado en `crypto_jobs.error` (sin texto)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RotationBusy(Exception):
    """Otro proceso tiene el candado de la clase (`lock`) o la base sigue ocupada tras los
    reintentos."""

    def __init__(self, *, lock: bool = False) -> None:
        super().__init__("lock" if lock else "busy")
        self.lock = lock


# Cupo de rotadores del proceso -------------------------------------------------------------


def try_claim_slot() -> bool:
    """Reserva el cupo (síncrono: sin `await` no hay carrera entre dos peticiones)."""
    global _slots_used
    if _slots_used >= ROTATION_SLOTS:
        return False
    _slots_used += 1
    return True


def release_slot() -> None:
    global _slots_used
    _slots_used = max(0, _slots_used - 1)


def track(state: State, tarea: asyncio.Task[None]) -> None:
    """Guarda la tarea en `state.rotation_tasks` (se quita sola al terminar) y como
    `state.rotation_task` (la última); el `finally` del lifespan las cancela todas."""
    tareas: set[asyncio.Task[None]] = getattr(state, "rotation_tasks", None) or set()
    state.rotation_tasks = tareas
    tareas.add(tarea)
    tarea.add_done_callback(tareas.discard)
    state.rotation_task = tarea


def launch(session_factory: async_sessionmaker[AsyncSession], job_id: UUID) -> asyncio.Task[None]:
    """Lanza la tarea de un cupo ya reservado; el cupo se libera al terminar o cancelarse."""
    tarea = asyncio.create_task(run_rotation(session_factory, job_id), name="key-rotation")
    tarea.add_done_callback(lambda _t: release_slot())
    return tarea


# Motor y candado -----------------------------------------------------------------------------


def rotation_engine(settings: Settings | None, *, bind_url: URL | None = None) -> AsyncEngine:
    """Motor dedicado (`pool_size=1`, `max_overflow=0`) para el candado de sesión.

    Con `Settings`, la URL y los tiempos de espera del api; sin ellos (herramientas y pruebas sin
    configuración), la URL del motor de la fábrica de sesiones."""
    if settings is not None:
        url: str | URL = settings.DATABASE_URL.get_secret_value()
        servidor = server_settings_from(settings)
    elif bind_url is not None:
        url, servidor = bind_url, {}
    else:
        raise RuntimeError("rotation_engine necesita Settings o la URL del motor")
    return create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"timeout": CONNECT_TIMEOUT_S, "server_settings": servidor},
    )


@asynccontextmanager
async def _class_lock(engine: AsyncEngine, data_class: str) -> AsyncIterator[None]:
    """Candado de sesión `apex:rotate:<clase>` (el de `service`) en la conexión del motor dedicado:
    la sesión solo sirve para que `service.rotation_lock` encuentre el motor; no ejecuta nada."""
    async with async_sessionmaker(bind=engine)() as sesion:
        try:
            async with service.rotation_lock(sesion, data_class):
                yield
        except service.RotationInProgress:
            raise RotationBusy(lock=True) from None


# Piezas del bucle ----------------------------------------------------------------------------


async def retry[T](operation: Callable[[], Awaitable[T]]) -> T:
    """Un intento y `RETRIES` reintentos ante `DatabaseBusy`; agotados, `RotationBusy`."""
    for intento in range(RETRIES + 1):
        try:
            return await operation()
        except DatabaseBusy:
            if intento == RETRIES:
                break
            await asyncio.sleep(WAIT_S)
    raise RotationBusy


async def _in_job[T](
    factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    work: Callable[[AsyncSession, CryptoJob], Awaitable[T]],
) -> tuple[T, int, int]:
    """Una transacción corta sobre el job recargado: el trabajo y su avance `(hecho, total)`."""
    async with factory() as session, session.begin():
        job = await session.get(CryptoJob, job_id, populate_existing=True)
        if job is None:
            raise RotationFailed("job_missing")
        resultado = await work(session, job)
        return resultado, job.done, job.total


async def _fail(factory: async_sessionmaker[AsyncSession], job_id: UUID, code: str) -> None:
    """Marca `failed` el job en curso (su propia transacción); `code` es un código, no texto."""
    cambio = update(CryptoJob).where(CryptoJob.id == job_id, CryptoJob.status.in_(OPEN_STATES))
    try:
        async with factory() as session, session.begin():
            await session.execute(
                cambio.values(
                    status="failed",
                    error=code[: service.MAX_ERROR_LENGTH],
                    finished_at=current_clock().now_utc(),
                )
            )
    except Exception as e:  # el job queda como estaba; el aviso sale igual
        logger.warning(
            "rotación: no se pudo marcar el job como failed",
            extra={"job_id": str(job_id), "error": type(e).__name__},
        )


async def _reload_keyring(factory: async_sessionmaker[AsyncSession]) -> None:
    """La llave nueva ya está en la base; el keyring de este proceso la aprende aquí."""
    keyring = current_keyring()
    if keyring.resolver is not None:
        async with factory() as session, session.begin():
            await keyring.load_all(session, keyring.resolver)


def _batch_size(data_class: str, pedido: int | None) -> int:
    """Con puerto `Reencryptor` el lote nunca pasa de `BATCH_FILES`: el puerto recorta y un pedido
    mayor haría que `migradas < size` pareciera una pasada vacía (V11)."""
    if get_reencryptor(data_class) is not None:
        return BATCH_FILES if pedido is None else min(pedido, BATCH_FILES)
    return BATCH_ROWS if pedido is None else pedido


async def _guarded[T](
    factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    work: Callable[[AsyncSession, CryptoJob], Awaitable[T]],
) -> tuple[T, int, int]:
    """`_in_job` con reintentos; un error con código deja el job `failed` (`RotationFailed`)."""
    try:
        return await retry(lambda: _in_job(factory, job_id, work))
    except (RotationBusy, RotationFailed):
        raise
    except Exception as error:
        codigo = str(getattr(error, "code", None) or type(error).__name__)
        await _fail(factory, job_id, codigo)
        raise RotationFailed(codigo) from None


async def _batch(
    factory: async_sessionmaker[AsyncSession], job_id: UUID, size: int
) -> tuple[int, int, int]:
    return await _guarded(factory, job_id, lambda s, j: service.reencrypt_batch(s, j, size))


async def _finish(factory: async_sessionmaker[AsyncSession], job_id: UUID) -> bool:
    cerrada, _, _ = await _guarded(factory, job_id, lambda s, j: service.finish_rotation(s, j))
    return cerrada


async def _loop(
    factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    size: int,
    on_progress: Callable[[int, int], None] | None,
) -> None:
    inicio = current_clock().now_utc()
    vacias = 0
    while True:
        if (current_clock().now_utc() - inicio).total_seconds() > ROTATION_MAX_S:
            await _fail(factory, job_id, "timeout")
            raise RotationFailed("timeout")
        migradas, hecho, total = await _batch(factory, job_id, size)
        if migradas and on_progress is not None:
            on_progress(hecho, total)
        if migradas:
            vacias = 0  # hubo avance: las pasadas vacías cuentan solo si son seguidas
        if migradas >= size:
            continue
        if await _finish(factory, job_id):
            return
        vacias += 1  # filas saltadas por estar bloqueadas: se espera y se vuelve a pasar
        await asyncio.sleep(WAIT_S)
        if vacias >= EMPTY_PASSES:
            await _fail(factory, job_id, "pending_records")
            raise RotationFailed("pending_records")


@contextmanager
def _acting_as(job_actor: UUID) -> Iterator[None]:
    """El actor del contexto (CLI `--as`, petición) manda; sin él, quien abrió el job."""
    if current_actor.get() is not None:
        yield
        return
    with actor_scope(job_actor):
        yield


def _dedicated_engine(factory: async_sessionmaker[AsyncSession]) -> AsyncEngine:
    """Motor dedicado con los `Settings` del proceso o, si no hay, con la URL de la fábrica."""
    try:
        settings: Settings | None = get_settings()
    except Exception:  # sin configuración (herramientas, pruebas): se usa la URL de la fábrica
        settings = None
    bind = factory.kw.get("bind")
    url = bind.url if isinstance(bind, AsyncEngine) else None
    return rotation_engine(settings, bind_url=url)


# Puntos de entrada ---------------------------------------------------------------------------


async def execute_rotation(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    *,
    batch_size: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """La rotación del job `job_id` hasta `done`; `RotationFailed` o `RotationBusy` si no."""
    async with session_factory() as session:
        job = await session.get(CryptoJob, job_id)
        if job is None or job.data_class is None or job.status not in OPEN_STATES:
            return
        clase, quien = job.data_class, job.created_by
    motor = _dedicated_engine(session_factory)
    try:
        async with _class_lock(motor, clase):
            with _acting_as(quien):
                oplog.begin_unit_of_work()  # buffer propio: la tarea no comparte el del request
                await _reload_keyring(session_factory)
                await _loop(session_factory, job_id, _batch_size(clase, batch_size), on_progress)
    finally:
        await motor.dispose()


async def run_rotation(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    *,
    batch_size: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Como `execute_rotation`, pero un fallo se anota en el log y el job queda como corresponde
    (`failed` con su código, o `running` si no se pudo ni empezar): nunca se relanza."""
    try:
        await execute_rotation(
            session_factory, job_id, batch_size=batch_size, on_progress=on_progress
        )
    except RotationFailed as error:
        logger.warning(
            "rotación fallida (%s)", error.code, extra={"job_id": str(job_id), "code": error.code}
        )
    except RotationBusy:
        logger.warning(
            "rotación pospuesta: candado ajeno o base ocupada", extra={"job_id": str(job_id)}
        )
    except Exception as error:
        logger.error(
            "rotación fallida sin código",
            extra={"job_id": str(job_id), "tipo": type(error).__name__},
        )
        await _fail(session_factory, job_id, type(error).__name__)


async def resume_running_jobs(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Termina los jobs `rotate` abiertos que dejó un reinicio; sin keyring, solo lo anota."""
    async with session_factory() as session:
        filas = await session.scalars(
            select(CryptoJob.id)
            .where(CryptoJob.kind == "rotate", CryptoJob.status == "running")
            .order_by(CryptoJob.created_at)
        )
        pendientes: list[UUID] = list(filas)
    if not pendientes:
        return
    if not recovery.is_loaded():
        logger.warning(
            "hay %d rotaciones sin terminar y el keyring no está cargado; se reanudan al cargarlo",
            len(pendientes),
        )
        return
    for job_id in pendientes:
        if not try_claim_slot():
            logger.warning("rotación sin reanudar: ya hay otra en vuelo")
            return
        try:
            await run_rotation(session_factory, job_id)
        finally:
            release_slot()
