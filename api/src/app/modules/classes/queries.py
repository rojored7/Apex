"""Lecturas de sesiones (S7-B2, US-157; S7-D11, S7-D20). Privado del módulo.

- `list_sessions(session, query, page, q=None)`: las sesiones de una semana ISO (`week`) o de un
  rango de fechas de Bogotá (`from`/`to`, hasta 62 días), por hora de inicio; sin fechas, la
  semana actual. Filtra por `q` (nombre, sin tildes), `coach_id` y `status` (`done` se calcula:
  programada cuya hora de fin ya pasó).
- `get_session(session, session_id)`: una sesión con sus asistentes (llegan con C1; hoy `[]`).
- `session_out(...)`: arma `SessionOut` con el estado calculado y el nombre del coach.
`attendance_count` es 0 hasta C1 (la tabla de asistencia no existe todavía).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, Text, and_, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.auth import service as auth_service
from app.modules.classes.exceptions import ClassValidationError, RangeTooLong, SessionNotFound
from app.modules.classes.models import ClassSession
from app.modules.classes.rules import (
    MAX_RANGE_DAYS,
    WEEK_YEAR_MAX,
    WEEK_YEAR_MIN,
    date_range_utc,
    parse_week,
    session_status,
    week_of,
    week_range,
)
from app.modules.classes.schemas import SessionDetail, SessionListQuery, SessionOut


def session_out(row: ClassSession, names: dict[UUID, str], now: datetime) -> SessionOut:
    """`SessionOut` de una fila; `status` es el calculado (`done` incluido)."""
    coach = row.coach_id
    return SessionOut.model_validate(
        {
            "id": row.id,
            "slot_id": row.slot_id,
            "session_date": row.session_date,
            "starts_at": row.starts_at,
            "duration_min": row.duration_min,
            "capacity": row.capacity,
            "coach_id": coach,
            "coach_name": names.get(coach) if coach is not None else None,
            "name": row.name,
            "status": session_status(row.status, row.starts_at, row.duration_min, now),
            "attendance_count": 0,
            "cancel_reason": row.cancel_reason,
            "cancelled_at": row.cancelled_at,
        }
    )


async def _outs(session: AsyncSession, rows: list[ClassSession]) -> list[SessionOut]:
    ids = [r.coach_id for r in rows if r.coach_id is not None]
    nombres = await auth_service.user_names_for(session, ids) if ids else {}
    ahora = current_clock().now_utc()
    return [session_out(r, nombres, ahora) for r in rows]


def _range_error(field: str, message: str) -> ClassValidationError:
    return ClassValidationError(message=message, field=field)


def _window(query: SessionListQuery, today: date) -> tuple[datetime, datetime]:
    """`[desde, hasta)` en UTC de la consulta, o 422."""
    hay_rango = query.from_date is not None or query.to_date is not None
    if query.week is not None and hay_rango:
        raise _range_error("week", "Usa `week` o `from` y `to`, no los dos.")
    if query.week is not None:
        return week_range(*parse_week(query.week))
    if not hay_rango:
        return week_range(*parse_week(week_of(today)))
    if query.from_date is None or query.to_date is None:
        campo = "to" if query.to_date is None else "from"
        raise _range_error(campo, "Indica `from` y `to` juntos.")
    for campo, valor in (("from", query.from_date), ("to", query.to_date)):
        if not WEEK_YEAR_MIN <= valor.year <= WEEK_YEAR_MAX:  # S7-B2b: evita el desborde de fechas
            raise _range_error(campo, "Las fechas deben estar entre 2020 y 2100.")
    if query.to_date < query.from_date:
        raise _range_error("to", "`to` no puede ser anterior a `from`.")
    if (query.to_date - query.from_date).days + 1 > MAX_RANGE_DAYS:
        raise RangeTooLong()
    return date_range_utc(query.from_date, query.to_date)


def _status_filter(status: str, now: datetime) -> Any:
    fin = ClassSession.starts_at + func.make_interval(
        literal(0, Integer),
        literal(0, Integer),
        literal(0, Integer),
        literal(0, Integer),
        literal(0, Integer),
        ClassSession.duration_min,
    )
    if status == "cancelled":
        return ClassSession.status == "cancelled"
    programada = ClassSession.status == "scheduled"
    return and_(programada, fin <= now) if status == "done" else and_(programada, fin > now)


async def list_sessions(
    session: AsyncSession, query: SessionListQuery, page: PageParams, *, q: str | None = None
) -> Page[SessionOut]:
    """`GET /class-sessions` (docstring del módulo)."""
    reloj = current_clock()
    desde, hasta = _window(query, reloj.today_bogota())
    consulta = select(ClassSession).where(
        ClassSession.starts_at >= desde, ClassSession.starts_at < hasta
    )
    termino = clean_query(q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(
            sql_fold(func.coalesce(ClassSession.name, "")).ilike(patron, escape=LIKE_ESCAPE)
        )
    if query.coach_id is not None:
        consulta = consulta.where(ClassSession.coach_id == query.coach_id)
    if query.status is not None:
        consulta = consulta.where(_status_filter(query.status, reloj.now_utc()))
    filas, total = await paginate(
        session, consulta.order_by(ClassSession.starts_at, ClassSession.id), page
    )
    return to_page(await _outs(session, list(filas)), total, page)


async def get_session(session: AsyncSession, session_id: UUID) -> SessionDetail:
    """`GET /class-sessions/{id}`: la sesión y sus asistentes (vacía hasta C1)."""
    fila = await session.get(ClassSession, session_id)
    if fila is None:
        raise SessionNotFound()
    (salida,) = await _outs(session, [fila])
    return SessionDetail(**salida.model_dump(), attendees=[])
