"""Bitácora de corridas del worker: `worker.job_runs` (US-113; S4A-D3, S4A-D38, S4A-D55).

- `JobRun`: una fila por `(job_name, run_date)` (fecha civil de Bogotá). Sin `__audited__`: es
  bitácora operativa, no dato de negocio (`tests/architecture/test_audited_tables.py`,
  `EXCLUIDAS`). La tabla nace en `0012_worker_job_runs`.
- `claim_run`: reclama la fila del día con `INSERT ... ON CONFLICT DO UPDATE` (Core, sin
  `text()`); `None` si otra corrida `running` sigue vigente (menos de `stale_after`) o, con
  `reclaim_finished=False` (el ciclo programado, S4A-D79), si el día ya tiene un intento cerrado.
  Reclamar una `running` vencida deja en `details["attempts"]` un intento `stale` (S4A-D78). El
  actor ya viene fijado por el runner (`actor_scope` antes del reclamo, S4A-D55 a); sin actor
  lanza `MissingActorError` antes de escribir.
- `finish_run`: cierra el intento reclamado con un solo `UPDATE ... RETURNING` condicionado a
  `result = 'running'` y `started_at = claimed_started_at` (S4A-D77): si la fila ya no es de ese
  intento (otro proceso la reclamó por vencida, o ya se cerró) no escribe y devuelve `None`. El
  intento se agrega a `attempts` y se recorta en la misma sentencia. `error` solo es el nombre del
  tipo de la excepción (`type(exc).__name__`) y `details` solo admite claves de `DETAIL_KEYS` con
  valores enteros, más `clock_override` (booleano); `attempts` lo escribe la sentencia (máximo
  `MAX_ATTEMPTS`). Cualquier otra cosa lanza `ValueError` sin escribir (S4A-D55 d).
- `last_run`: el último intento de un `job_name` exacto (`expirations` nunca devuelve
  `expirations_sim`, S4A-D48).

Solo `app.worker.*` importa este archivo (`tests/architecture/test_worker_boundaries.py`,
S4A-D73); `migrations/env.py` y las pruebas también. No importa `app.modules` ni `core/audit`.
Ninguna función confirma: quien llama abre una sesión corta y propia y hace `commit`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import (
    TIMESTAMP,
    ColumnElement,
    Date,
    Row,
    Text,
    and_,
    case,
    func,
    literal,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.db import Base, CommonColumnsMixin

DETAIL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "revisados",
        "cambiadas",
        "por_vencer",
        "vencidas",
        "otras",
        "busy_omitidos",
        "errores",
        "placeholder_ok",
    }
)
"""Claves enteras admitidas en `details` (S4A-D55 d); `attempts` y `clock_override` aparte."""

MAX_ATTEMPTS: Final = 20
"""Intentos que conserva `details["attempts"]` (los más recientes)."""

ATTEMPTS_PATH: Final = "$[last - 19 to last]"
"""jsonpath de los `MAX_ATTEMPTS` intentos más recientes (una prueba fija la paridad)."""

DEFAULT_STALE_AFTER: Final = timedelta(hours=6)
"""Valor por defecto de `claim_run`; el runner pasa `STALE_FACTOR * timeout_s` (S4A-D55)."""

RESULTS: Final[frozenset[str]] = frozenset(
    {"running", "ok", "error", "ok_unverified", "stale", "missing", "corrupt", "undecryptable"}
)
"""Valores del CHECK de `result` en `0012` (los de backup son de US-115, v0.2)."""

RUNNING: Final = "running"
STALE_RESULT: Final = "stale"
CLOCK_OVERRIDE_KEY: Final = "clock_override"
ATTEMPTS_KEY: Final = "attempts"
MAX_ERROR_LENGTH: Final = 128


class JobRun(CommonColumnsMixin, Base):
    """Fila de `worker.job_runs` (S4A-D38). Sin `__audited__` (bitácora operativa)."""

    __tablename__ = "job_runs"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


@dataclass(frozen=True)
class JobRunView:
    """Vista inmutable de una fila de `worker.job_runs` (S4A-D3)."""

    id: UUID
    job_name: str
    run_date: date
    started_at: datetime
    finished_at: datetime | None
    result: str
    error: str | None
    details: dict[str, Any]


def _vista(fila: Row[Any]) -> JobRunView:
    return JobRunView(
        id=fila.id,
        job_name=fila.job_name,
        run_date=fila.run_date,
        started_at=fila.started_at,
        finished_at=fila.finished_at,
        result=fila.result,
        error=fila.error,
        details=dict(fila.details or {}),
    )


_COLUMNAS_VISTA = (
    JobRun.id,
    JobRun.job_name,
    JobRun.run_date,
    JobRun.started_at,
    JobRun.finished_at,
    JobRun.result,
    JobRun.error,
    JobRun.details,
)


def _attempt(
    started_at: Any,
    finished_at: Any,
    result: str,
    error: str | None,
) -> ColumnElement[Any]:
    """Un intento `{started_at, finished_at, result, error}` armado en la base."""
    return func.jsonb_build_object(
        "started_at",
        started_at,
        "finished_at",
        finished_at,
        "result",
        literal(result, Text),
        "error",
        literal(error, Text),
        type_=JSONB,
    )


def _with_attempt(attempt: ColumnElement[Any]) -> ColumnElement[Any]:
    """`{"attempts": [...previos, attempt]}` recortado a `MAX_ATTEMPTS`, leído de la propia fila."""
    previos = func.coalesce(JobRun.details.op("->")(ATTEMPTS_KEY), literal([], JSONB))
    lista = func.jsonb_path_query_array(
        previos.op("||")(func.jsonb_build_array(attempt, type_=JSONB)),
        literal(ATTEMPTS_PATH, JSONPATH),
        type_=JSONB,
    )
    return func.jsonb_build_object(ATTEMPTS_KEY, lista, type_=JSONB)


async def claim_run(
    session: AsyncSession,
    job_name: str,
    run_date: date,
    *,
    now: datetime,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
    reclaim_finished: bool = True,
) -> JobRunView | None:
    """Reclama `(job_name, run_date)`; `None` si no se puede (ver docstring del módulo).

    El actor se lee antes de construir la sentencia (S4A-D55 a). Una fila previa del día se
    reutiliza (conserva `id`, `created_by` y `details`) si su `running` empezó antes de
    `now - stale_after` (y se anota el intento `stale`) o, con `reclaim_finished`, si ya está
    cerrada (el reintento manual de `--run-once`).
    """
    actor = get_actor()
    nueva = insert(JobRun).values(
        id=uuid4(),
        job_name=job_name,
        run_date=run_date,
        started_at=now,
        finished_at=None,
        result=RUNNING,
        error=None,
        created_by=actor,
    )
    vencida = and_(JobRun.result == RUNNING, JobRun.started_at < now - stale_after)
    rastro = _attempt(JobRun.started_at, literal(now, TIMESTAMP(timezone=True)), STALE_RESULT, None)
    sentencia = nueva.on_conflict_do_update(
        index_elements=[JobRun.job_name, JobRun.run_date],
        set_={
            "started_at": nueva.excluded.started_at,
            "finished_at": None,
            "result": RUNNING,
            "error": None,
            "details": case(
                (vencida, JobRun.details.op("||")(_with_attempt(rastro))), else_=JobRun.details
            ),
            "updated_at": func.now(),
        },
        where=or_(vencida, JobRun.result != RUNNING) if reclaim_finished else vencida,
    ).returning(*_COLUMNAS_VISTA)
    fila = (await session.execute(sentencia)).one_or_none()
    return None if fila is None else _vista(fila)


def _validar_error(error: str | None) -> None:
    """`error` es solo el nombre de un tipo (`type(exc).__name__`), nunca un mensaje."""
    if error is None:
        return
    if not error.isidentifier() or len(error) > MAX_ERROR_LENGTH:
        raise ValueError("finish_run: error debe ser el nombre del tipo de la excepción")


def check_details(details: Mapping[str, Any]) -> None:
    """Claves cerradas: enteros de `DETAIL_KEYS` y `clock_override` booleano (S4A-D55 d).

    Pública para el runner: valida lo que devuelve un job antes de darlo por `ok` (S4A-D76).
    """
    for clave, valor in details.items():
        if clave == CLOCK_OVERRIDE_KEY:
            if not isinstance(valor, bool):
                raise ValueError("finish_run: clock_override debe ser booleano")
        elif clave not in DETAIL_KEYS:
            raise ValueError(f"finish_run: clave de details no admitida: {clave!r}")
        elif type(valor) is not int:
            raise ValueError(f"finish_run: {clave} debe ser un entero")


def _validar_resultado(result: str) -> None:
    if result not in RESULTS or result == RUNNING:
        raise ValueError(f"finish_run: result no admitido: {result!r}")


async def finish_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    claimed_started_at: datetime,
    result: str,
    error: str | None,
    details: dict[str, Any],
) -> JobRunView | None:
    """Cierra el intento reclamado; `None` si la fila ya no es de ese intento (S4A-D77).

    Valida antes de escribir (`ValueError`). Un solo `UPDATE ... RETURNING`: reemplaza los conteos
    por los de este intento y agrega el intento a `attempts` leyendo la propia fila. `finished_at`
    es el instante del reloj del proceso, nunca anterior a `started_at` (CHECK de `0012`, S4A-D80).
    """
    _validar_resultado(result)
    _validar_error(error)
    check_details(details)
    fin = func.greatest(
        literal(current_clock().now_utc(), TIMESTAMP(timezone=True)), JobRun.started_at
    )
    intento = _attempt(JobRun.started_at, fin, result, error)
    sentencia = (
        update(JobRun)
        .where(
            JobRun.id == run_id,
            JobRun.result == RUNNING,
            JobRun.started_at == claimed_started_at,
        )
        .values(
            result=result,
            error=error,
            finished_at=fin,
            details=literal(dict(details), JSONB).op("||")(_with_attempt(intento)),
            updated_at=func.now(),
        )
        .returning(*_COLUMNAS_VISTA)
    )
    fila = (await session.execute(sentencia)).one_or_none()
    return None if fila is None else _vista(fila)


async def last_run(session: AsyncSession, job_name: str) -> JobRunView | None:
    """El último intento (por `started_at DESC`) del `job_name` exacto."""
    fila = (
        await session.execute(
            select(*_COLUMNAS_VISTA)
            .where(JobRun.job_name == job_name)
            .order_by(JobRun.started_at.desc())
            .limit(1)
        )
    ).one_or_none()
    return None if fila is None else _vista(fila)
