"""Verificación de la cadena desde el api (privado de `audit`; S4A-D13, S4A-D18, S4A-D44, S4A-D47).

- `acquire_verify_lock()`: abre una conexión dedicada (`db.get_engine().connect()`), la pasa a
  `AUTOCOMMIT` (`await conn.execution_options(isolation_level="AUTOCOMMIT")`: sin transacción
  abierta, `idle_in_transaction_session_timeout` no la corta, H-2) y corre `TRY_LOCK_SQL` con
  `AUDIT_VERIFY_LOCK_KEY`. Devuelve la conexión con el candado o `None` (y la cierra) si otro lo
  tiene. Única excepción a L-11 junto con `core/audit_verify.py` (`test_guarded_calls.py`).
- `release_verify_lock(conn)`: intenta `UNLOCK_SQL` y, pase lo que pase, `await conn.invalidate()`
  en el `finally` (cierre físico: el candado de sesión nunca vuelve al pool). Nunca lanza: si el
  `unlock` falla, registra solo el tipo de la excepción.
- `verify(session, *, by)`: toma el candado ANTES de responder (409 `VerificationRunning`
  determinista); hasta `SYNC_VERIFY_MAX_ROWS` filas (`max(seq)`) corre `run_verification` en la
  sesión de la petición (en un SAVEPOINT, bajo `SYNC_VERIFY_MAX_SECONDS`) y devuelve
  `Finished(result)`; si ese plazo vence, o por encima del umbral, crea una tarea con su propia
  sesión bajo `asyncio.timeout(VERIFY_MAX_SECONDS)`, la guarda en `_BACKGROUND_TASKS` (y la quita
  al terminar) y devuelve `Started(last)`. La tarea libera el candado en su `finally` y, si falla o
  vence, no deja fila y registra solo el tipo.
- `last_verification(session)`: la última verificación por `finished_at` (`ok` o no), o `None`.
- `cancel_background_verifications()`: el `shutdown` del lifespan cancela las tareas y espera su
  `finally` (sueltan el candado) antes de cerrar el engine; el candado de una tarea cancelada
  antes de su primer paso lo suelta ella misma (S4A-D101).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core import audit_verify, db
from app.core.audit import AuditEntry
from app.core.audit_verify import (
    TRY_LOCK_STATEMENT,
    UNLOCK_STATEMENT,
    AuditVerification,
    VerificationView,
    run_verification,
    view_of,
)
from app.modules.audit.exceptions import VerificationRunning

logger = logging.getLogger("app.audit")

SYNC_VERIFY_MAX_ROWS: Final = 100_000
"""Umbral síncrono (S4A-D13, contradicción 3), calibrado en B3.12 con `test_verify_performance.py`:
100.000 filas con lotes de 1.000 tardan ~2,4 s (< 20 s), así que sube de 50.000 a 100.000 (la
regla de la contradicción 3 de `DECISIONES.md`). Con el lote de 500 por rango acotado (S4A-D120)
siguen en ~2,5 s."""

SYNC_VERIFY_MAX_SECONDS: Final = 45
"""Plazo de la rama síncrona (S4A-D100): por debajo de los 60 s de Nginx. Si vence, la petición
revierte su SAVEPOINT y la verificación sigue en segundo plano con el mismo candado (202)."""

_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
"""Tareas 202 en curso (el recolector no las recoge; el `shutdown` las cancela)."""
_TASK_LOCKS: dict[asyncio.Task[None], AsyncConnection] = {}
"""La conexión del candado de cada tarea 202 hasta que su `finally` la suelta: si el `shutdown`
cancela una tarea antes de su primer paso, su `finally` nunca corre y la suelta
`cancel_background_verifications` (S4A-D101)."""


@dataclass(frozen=True)
class Finished:
    """La verificación terminó dentro de la petición (200)."""

    result: VerificationView


@dataclass(frozen=True)
class Started:
    """La verificación sigue en segundo plano (202); `last` es la última terminada."""

    last: VerificationView | None


async def acquire_verify_lock() -> AsyncConnection | None:
    """Conexión `AUTOCOMMIT` con el candado `4_270_003`, o `None` si otro lo tiene."""
    conn = await db.get_engine().connect()
    try:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        obtenido = await conn.scalar(
            TRY_LOCK_STATEMENT, {"key": audit_verify.AUDIT_VERIFY_LOCK_KEY}
        )
    except BaseException:
        await conn.invalidate()
        raise
    if obtenido:
        return conn
    await conn.invalidate()
    return None


def _log_failure(mensaje: str, error_type: str | None) -> None:
    """Registra solo el tipo (sin traza ni mensaje: pueden traer datos). Se llama FUERA de los
    `except`, como en S4A-D90: si un handler falla, `handleError` no encadena la excepción."""
    if error_type is not None:
        logger.warning(mensaje, extra={"error_type": error_type})


async def _invalidate_quietly(conn: AsyncConnection) -> str | None:
    """`invalidate()` (cierre físico: el candado de sesión nunca vuelve al pool); el tipo del
    fallo, o `None`."""
    try:
        await conn.invalidate()
    except Exception as exc:  # nunca lanza (S4A-D44)
        return type(exc).__name__
    return None


async def release_verify_lock(conn: AsyncConnection) -> None:
    """`pg_advisory_unlock` y, siempre, `invalidate()`; nunca lanza."""
    unlock_error: str | None = None
    invalidate_error: str | None = None
    try:
        await conn.scalar(UNLOCK_STATEMENT, {"key": audit_verify.AUDIT_VERIFY_LOCK_KEY})
    except Exception as exc:  # invalidar suelta el candado igual
        unlock_error = type(exc).__name__
    finally:
        invalidate_error = await _invalidate_quietly(conn)
    _log_failure("audit verify unlock failed", unlock_error)
    _log_failure("audit verify invalidate failed", invalidate_error)


async def _run_in_background(conn: AsyncConnection, by: UUID) -> None:
    """La verificación 202: sesión propia bajo `VERIFY_MAX_SECONDS`; suelta el candado siempre.
    Un fallo o el plazo vencido (`TimeoutError`) no dejan fila (la transacción se revierte) y
    registran solo el tipo; la cancelación (shutdown) se propaga tras soltar el candado."""
    error_type: str | None = None
    try:
        async with asyncio.timeout(audit_verify.VERIFY_MAX_SECONDS):
            async with db.get_sessionmaker()() as session, session.begin():
                await run_verification(session, source="api", by=by)
    except Exception as exc:  # la tarea no tiene a quién propagar
        error_type = type(exc).__name__
    except asyncio.CancelledError:
        error_type = "CancelledError"
        raise
    finally:
        tarea = asyncio.current_task()
        if tarea is not None:
            _TASK_LOCKS.pop(tarea, None)
        await release_verify_lock(conn)
        _log_failure("audit verify failed", error_type)


def _start_in_background(conn: AsyncConnection, by: UUID) -> None:
    tarea = asyncio.create_task(_run_in_background(conn, by))
    _BACKGROUND_TASKS.add(tarea)
    _TASK_LOCKS[tarea] = conn
    tarea.add_done_callback(_BACKGROUND_TASKS.discard)


async def _verify_in_request(
    session: AsyncSession, by: UUID
) -> tuple[VerificationView | None, VerificationView | None]:
    """`(resultado, None)` si termina dentro de `SYNC_VERIFY_MAX_SECONDS`; si vence, revierte su
    SAVEPOINT y devuelve `(None, última)` para seguir en segundo plano (S4A-D100). La sesión de la
    petición no escribió auditoría antes: `record` (que toma el candado de la cadena `4_270_002`
    hasta el commit) solo corre en `_persist`, al final del recorrido (S4A-D102)."""
    last = await last_verification(session)
    try:
        async with asyncio.timeout(SYNC_VERIFY_MAX_SECONDS), session.begin_nested():
            return await run_verification(session, source="api", by=by), None
    except TimeoutError:
        return None, last


async def verify(session: AsyncSession, *, by: UUID) -> Finished | Started:
    """Ver el docstring del módulo. Lanza `VerificationRunning` si el candado está tomado."""
    conn = await acquire_verify_lock()
    if conn is None:
        raise VerificationRunning()
    en_segundo_plano = False
    try:
        maximo = await session.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
        if int(maximo or 0) <= SYNC_VERIFY_MAX_ROWS:
            resultado, last = await _verify_in_request(session, by)
            if resultado is not None:
                return Finished(resultado)
        else:
            last = await last_verification(session)
        _start_in_background(conn, by)
        en_segundo_plano = True
        return Started(last)
    finally:
        if not en_segundo_plano:
            await release_verify_lock(conn)


async def last_verification(session: AsyncSession) -> VerificationView | None:
    """La última verificación guardada (por `finished_at`, `ok` o no), o `None`."""
    row = await session.scalar(
        select(AuditVerification)
        .order_by(AuditVerification.finished_at.desc(), AuditVerification.created_at.desc())
        .limit(1)
    )
    return None if row is None else view_of(row)


async def cancel_background_verifications() -> None:
    """Cancela las tareas 202 en curso y espera su `finally` (sueltan el candado). Una tarea
    cancelada antes de su primer paso no corre su `finally`: su candado se suelta aquí."""
    tareas = list(_BACKGROUND_TASKS)
    for tarea in tareas:
        tarea.cancel()
    if tareas:
        await asyncio.gather(*tareas, return_exceptions=True)
    for tarea in tareas:
        conn = _TASK_LOCKS.pop(tarea, None)
        if conn is not None:
            await release_verify_lock(conn)
