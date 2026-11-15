"""Lecturas de sesiones (S7-B2, US-157; S7-D11, S7-D20). Privado del módulo.

- `list_sessions(session, query, page, q=None)`: las sesiones de una semana ISO (`week`) o de un
  rango de fechas de Bogotá (`from`/`to`, hasta 62 días), por hora de inicio; sin fechas, la
  semana actual. Filtra por `q` (nombre, sin tildes), `coach_id` y `status` (`done` se calcula:
  programada cuya hora de fin ya pasó).
  `wod_id` filtra por el WOD efectivo (S8-A4): el asignado o, sin asignar, el del día de ese WOD.
- `get_session(session, session_id)`: una sesión con sus asistentes vivos (C1, US-159).
- `session_out(...)`: arma `SessionOut` con el estado calculado y el nombre del coach.
`attendance_count` cuenta las asistencias vivas (`removed_at` nulo) de cada sesión.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Integer, Text, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.errors import ForbiddenError
from app.core.pagination import Page, PageParams, any_uuids, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.auth import service as auth_service
from app.modules.classes.exceptions import ClassValidationError, RangeTooLong, SessionNotFound
from app.modules.classes.models import Attendance, ClassSession
from app.modules.classes.rules import (
    MAX_RANGE_DAYS,
    WEEK_YEAR_MAX,
    WEEK_YEAR_MIN,
    date_range_utc,
    effective_wod_id,
    is_kiosk_day,
    local_date,
    parse_week,
    session_status,
    week_of,
    week_range,
)
from app.modules.classes.schemas import (
    AttendeeOut,
    SessionDetail,
    SessionListQuery,
    SessionOut,
)
from app.modules.members import service as members_service
from app.modules.wods import service as wods_service


async def attended_member_ids(session: AsyncSession, since_day: date | None) -> set[UUID]:
    """Ids de los socios con alguna asistencia viva (`removed_at` nulo) cuyo `checked_in_at` cae
    desde el inicio del día civil de Bogotá `since_day`; `None` = en cualquier fecha (US-163)."""
    consulta = select(Attendance.member_id).where(Attendance.removed_at.is_(None)).distinct()
    if since_day is not None:
        desde, _ = date_range_utc(since_day, since_day)
        consulta = consulta.where(Attendance.checked_in_at >= desde)
    return set(await session.scalars(consulta))


async def last_attendance_for(
    session: AsyncSession, member_ids: list[UUID]
) -> dict[UUID, datetime]:
    """Última asistencia viva (`checked_in_at`, UTC) de cada socio pedido que tenga una, en UNA
    consulta; sin ids no consulta (US-163)."""
    if not member_ids:
        return {}
    filas = await session.execute(
        select(Attendance.member_id, func.max(Attendance.checked_in_at))
        .where(Attendance.member_id == any_uuids(member_ids), Attendance.removed_at.is_(None))
        .group_by(Attendance.member_id)
    )
    return {socio: cuando for socio, cuando in filas.all()}


def session_out(
    row: ClassSession,
    names: dict[UUID, str],
    now: datetime,
    attendance_count: int = 0,
    day_wods: Mapping[date, UUID] | None = None,
) -> SessionOut:
    """`SessionOut` de una fila; `status` es el calculado (`done` incluido). `day_wods` es el WOD de
    cada día de Bogotá (una llamada por página, S8-D9): el efectivo es el asignado o el del día."""
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
            "attendance_count": attendance_count,
            "cancel_reason": row.cancel_reason,
            "cancelled_at": row.cancelled_at,
            "wod_id": row.wod_id,
            "effective_wod_id": effective_wod_id(
                row.wod_id, (day_wods or {}).get(row.session_date)
            ),
        }
    )


async def attendance_counts(session: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
    """Asistencias vivas por sesión, en una consulta."""
    if not ids:
        return {}
    filas = await session.execute(
        select(Attendance.session_id, func.count())
        .where(Attendance.session_id.in_(ids), Attendance.removed_at.is_(None))
        .group_by(Attendance.session_id)
    )
    return {sid: int(n) for sid, n in filas.all()}


async def _outs(session: AsyncSession, rows: list[ClassSession]) -> list[SessionOut]:
    ids = [r.coach_id for r in rows if r.coach_id is not None]
    nombres = await auth_service.user_names_for(session, ids) if ids else {}
    ahora = current_clock().now_utc()
    cuentas = await attendance_counts(session, [r.id for r in rows])
    por_dia = await wods_service.day_wod_ids(session, {r.session_date for r in rows})
    return [session_out(r, nombres, ahora, cuentas.get(r.id, 0), por_dia) for r in rows]


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
    if query.wod_id is not None:  # semántica efectiva (S8-D9): asignado, o heredado del día de X
        fecha = await wods_service.wod_date(session, query.wod_id)
        if fecha is None:
            return to_page([], 0, page)
        consulta = consulta.where(
            or_(
                ClassSession.wod_id == query.wod_id,
                and_(ClassSession.wod_id.is_(None), ClassSession.session_date == fecha),
            )
        )
    filas, total = await paginate(
        session, consulta.order_by(ClassSession.starts_at, ClassSession.id), page
    )
    return to_page(await _outs(session, list(filas)), total, page)


async def get_session(session: AsyncSession, session_id: UUID) -> SessionDetail:
    """`GET /class-sessions/{id}`: la sesión y sus asistentes vivos, por hora de llegada."""
    fila = await session.get(ClassSession, session_id)
    if fila is None:
        raise SessionNotFound()
    (salida,) = await _outs(session, [fila])
    presentes = list(
        (
            await session.scalars(
                select(Attendance)
                .where(Attendance.session_id == session_id, Attendance.removed_at.is_(None))
                .order_by(Attendance.checked_in_at, Attendance.id)
            )
        ).all()
    )
    socios = await members_service.names_for(session, [a.member_id for a in presentes])
    asistentes = [
        AttendeeOut(
            id=a.id,
            member_id=a.member_id,
            first_name=socios[a.member_id].first_name if a.member_id in socios else "",
            last_name=socios[a.member_id].last_name if a.member_id in socios else "",
            flagged=len(a.flags) > 0,
            flags=list(a.flags),
            checked_in_at=a.checked_in_at,
        )
        for a in presentes
    ]
    return SessionDetail(**salida.model_dump(), attendees=asistentes)


KIOSK_SESSION_MESSAGE: Final = "En modo quiosco solo ves las clases de hoy o de ayer."

TODAY_SESSIONS_LIMIT: Final = 50
"""Tope de `today_sessions` (US-164): el tablero nunca pinta más de 50 sesiones de un día."""


@dataclass(frozen=True, slots=True)
class WeekAttendance:
    """Asistencias vivas de la semana en curso y cuántas llevan alguna bandera (US-164)."""

    count: int
    flagged_count: int


async def week_attendance(session: AsyncSession, now: datetime) -> WeekAttendance:
    """Asistencias vivas de la semana en curso: del lunes 00:00 de Bogotá a `now` (US-164, Q28),
    y cuántas llevan alguna bandera; UNA consulta."""
    desde, _ = week_range(*parse_week(week_of(local_date(now))))
    fila = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(func.cardinality(Attendance.flags) > 0),
            ).where(
                Attendance.removed_at.is_(None),
                Attendance.checked_in_at >= desde,
                Attendance.checked_in_at <= now,
            )
        )
    ).one()
    return WeekAttendance(count=int(fila[0]), flagged_count=int(fila[1]))


async def today_sessions(session: AsyncSession, today: date) -> list[SessionOut]:
    """Las sesiones del día civil de Bogotá `today`, por hora (máximo `TODAY_SESSIONS_LIMIT`),
    con coach, ocupación y estado calculado, incluidas las canceladas (US-164)."""
    desde, hasta = date_range_utc(today, today)
    filas = await session.scalars(
        select(ClassSession)
        .where(ClassSession.starts_at >= desde, ClassSession.starts_at < hasta)
        .order_by(ClassSession.starts_at, ClassSession.id)
        .limit(TODAY_SESSIONS_LIMIT)
    )
    return await _outs(session, list(filas))


async def kiosk_session_info(session: AsyncSession, session_id: UUID) -> tuple[bool, str] | None:
    """`(en_ventana, status)` de una sesión, o `None` si no existe (S7-C4c, M-1): el puerto que
    `classes` registra en `auth` para la regla de cambio de clase del quiosco (S7-D42).
    `en_ventana` es `rules.is_kiosk_day` con el día de hoy de Bogotá (V7, L-2); `status` es el
    guardado (`scheduled` o `cancelled`), no el calculado."""
    fila = (
        await session.execute(
            select(ClassSession.session_date, ClassSession.status).where(
                ClassSession.id == session_id
            )
        )
    ).first()
    if fila is None:
        return None
    return is_kiosk_day(fila[0], current_clock().today_bogota()), fila[1]


async def ensure_kiosk_session(session: AsyncSession, session_id: UUID) -> None:
    """S7-D42 (L-2): en quiosco solo se ve la lista de una sesión de hoy o de ayer en Bogotá; otra
    o inexistente da 403 `kiosk_mode`."""
    info = await kiosk_session_info(session, session_id)
    if info is None or not info[0]:
        raise ForbiddenError("kiosk_mode", KIOSK_SESSION_MESSAGE)
