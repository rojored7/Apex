"""Reportes de asistencia (S7-R1, US-162; S7-D15, M-5). Privado del módulo.

- `check_summary_range(from_day, to_day)`: pura; 422 `field = "from"` si `from > to`, si un año
  sale de 2020 a 2100 o si el rango pasa de 26 semanas (182 días).
- `summary_rows(session, from_day, to_day, now)`: UNA consulta que agrega en SQL (`GROUP BY` semana
  ISO de Bogotá y franja) sobre las sesiones programadas que ya empezaron; la función pura no ve
  asistencias sueltas, solo filas ya agrupadas (M-5: nunca 26 semanas de filas en Python).
- `weekly_summary(rows, weeks=())`: pura; arma los `WeekBucket` desde las filas agrupadas.
- `attendance_summary(session, from_day, to_day)`: `GET /attendance/summary`.
- `member_attendance(session, member_id, page)`: `GET /members/{id}/attendance`; `get_ref` da 404
  solo si el socio no existe (uno dado de baja se ve, N-20).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Date, DateTime, Select, Subquery, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.pagination import Page, PageParams
from app.modules.classes.attendance import list_attendance
from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.models import Attendance, ClassSession, ClassSlot
from app.modules.classes.rules import WEEK_YEAR_MAX, WEEK_YEAR_MIN, week_of
from app.modules.classes.schemas import (
    AttendanceListQuery,
    AttendanceRowOut,
    AttendanceSummary,
    SlotBucket,
    WeekBucket,
)
from app.modules.members import service as members_service

SUMMARY_MAX_WEEKS: Final = 26
SUMMARY_MAX_DAYS: Final = SUMMARY_MAX_WEEKS * 7
EXTRA_LABEL: Final = "Extra"
_LAST_SLOT_KEY: Final = "99:99"


@dataclass(frozen=True, slots=True)
class SummaryRow:
    """Una fila ya agrupada por SQL: semana (lunes), franja y sus sumas."""

    week_start: date
    slot_id: UUID | None
    slot_name: str | None
    slot_start_time: str | None
    sessions: int
    attendance: int
    flagged: int
    capacity_sum: int


def _invalid(message: str) -> ClassValidationError:
    return ClassValidationError(message=message, field="from")


def check_summary_range(from_day: date, to_day: date) -> None:
    """422 `field = "from"`: años fuera de 2020 a 2100, `from > to` o más de 26 semanas."""
    for day in (from_day, to_day):
        if not WEEK_YEAR_MIN <= day.year <= WEEK_YEAR_MAX:
            raise _invalid("Las fechas deben estar entre 2020 y 2100.")
    if to_day < from_day:
        raise _invalid("`from` no puede ser posterior a `to`.")
    if (to_day - from_day).days + 1 > SUMMARY_MAX_DAYS:
        raise _invalid(f"El rango no puede pasar de {SUMMARY_MAX_WEEKS} semanas.")


def week_starts(from_day: date, to_day: date) -> list[date]:
    """Los lunes de las semanas ISO que tocan `[from_day, to_day]`."""
    lunes = from_day - timedelta(days=from_day.weekday())
    salida: list[date] = []
    while lunes <= to_day:
        salida.append(lunes)
        lunes += timedelta(days=7)
    return salida


def _percent(attendance: int, capacity: int) -> int:
    """Porcentaje entero, redondeo al más cercano (mitades hacia arriba); 0 con cupo 0."""
    if capacity <= 0:
        return 0
    return (attendance * 200 + capacity) // (2 * capacity)


def _slot_bucket(slot_id: UUID | None, rows: list[SummaryRow]) -> SlotBucket:
    primera = rows[0]
    attendance = sum(r.attendance for r in rows)
    capacity = sum(r.capacity_sum for r in rows)
    if slot_id is None:
        label, start = EXTRA_LABEL, None
    else:
        start = primera.slot_start_time
        label = primera.slot_name or start or "Franja"
    return SlotBucket(
        slot_id=slot_id,
        label=label,
        start_time=start,
        sessions=sum(r.sessions for r in rows),
        attendance=attendance,
        flagged=sum(r.flagged for r in rows),
        capacity_sum=capacity,
        occupancy_pct=_percent(attendance, capacity),
    )


def weekly_summary(rows: Iterable[SummaryRow], weeks: Sequence[date] = ()) -> list[WeekBucket]:
    """Arma las semanas desde filas ya agrupadas; `weeks` agrega las vacías (en cero).

    Sin E/S. Las sesiones extra (`slot_id` nulo) van en una sola franja «Extra», al final."""
    por_semana: dict[date, dict[UUID | None, list[SummaryRow]]] = {w: {} for w in weeks}
    for fila in rows:
        por_semana.setdefault(fila.week_start, {}).setdefault(fila.slot_id, []).append(fila)
    salida: list[WeekBucket] = []
    for lunes in sorted(por_semana):
        franjas = [_slot_bucket(sid, grupo) for sid, grupo in por_semana[lunes].items()]
        franjas.sort(
            key=lambda b: (
                b.slot_id is None,
                b.start_time or _LAST_SLOT_KEY,
                b.label,
                str(b.slot_id),
            )
        )
        salida.append(
            WeekBucket(
                week=week_of(lunes),
                week_start=lunes,
                total=sum(b.attendance for b in franjas),
                flagged=sum(b.flagged for b in franjas),
                slots=franjas,
            )
        )
    return salida


def _sessions_in_range(from_day: date, to_day: date, now: datetime) -> Select[Any]:
    """Ids de las sesiones que el resumen cuenta: programadas, ya empezadas y con
    `session_date` en `[from_day, to_day]` (los mismos predicados de `summary_rows`)."""
    return select(ClassSession.id).where(
        ClassSession.status == "scheduled",
        ClassSession.session_date >= from_day,
        ClassSession.session_date <= to_day,
        ClassSession.starts_at <= now,
    )


def _live_by_session(from_day: date, to_day: date, now: datetime) -> Subquery:
    """Asistencias vivas y marcadas por sesión (subconsulta; la base las suma por semana).

    Acotada a las sesiones del rango (R1b, M1): PG16 no empuja el filtro del `LEFT JOIN` dentro
    del `GROUP BY`, y sin este `IN` la subconsulta agrupaba toda la historia de asistencias."""
    return (
        select(
            Attendance.session_id.label("session_id"),
            func.count().label("n"),
            func.count().filter(func.cardinality(Attendance.flags) > 0).label("marcadas"),
        )
        .where(
            Attendance.removed_at.is_(None),
            Attendance.session_id.in_(_sessions_in_range(from_day, to_day, now)),
        )
        .group_by(Attendance.session_id)
        .subquery()
    )


async def summary_rows(
    session: AsyncSession, from_day: date, to_day: date, now: datetime
) -> list[SummaryRow]:
    """Una consulta: sesiones programadas que ya empezaron en `[from_day, to_day]` (días de
    Bogotá, `session_date`), con sus asistencias vivas contadas por sesión y sumadas por semana
    ISO y franja. Todo valor va ligado."""
    vivas = _live_by_session(from_day, to_day, now)
    semana = cast(func.date_trunc("week", cast(ClassSession.session_date, DateTime)), Date)
    consulta = (
        select(
            semana.label("week_start"),
            ClassSession.slot_id,
            ClassSlot.name,
            ClassSlot.start_time,
            func.count(ClassSession.id).label("sessions"),
            func.coalesce(func.sum(vivas.c.n), 0).label("attendance"),
            func.coalesce(func.sum(vivas.c.marcadas), 0).label("flagged"),
            func.sum(ClassSession.capacity).label("capacity_sum"),
        )
        .select_from(ClassSession)
        .outerjoin(vivas, vivas.c.session_id == ClassSession.id)
        .outerjoin(ClassSlot, ClassSlot.id == ClassSession.slot_id)
        .where(
            ClassSession.status == "scheduled",
            ClassSession.session_date >= from_day,
            ClassSession.session_date <= to_day,
            ClassSession.starts_at <= now,
        )
        .group_by(semana, ClassSession.slot_id, ClassSlot.name, ClassSlot.start_time)
    )
    return [
        SummaryRow(
            week_start=f.week_start,
            slot_id=f.slot_id,
            slot_name=f.name,
            slot_start_time=f.start_time,
            sessions=int(f.sessions),
            attendance=int(f.attendance),
            flagged=int(f.flagged),
            capacity_sum=int(f.capacity_sum),
        )
        for f in await session.execute(consulta)
    ]


async def attendance_summary(
    session: AsyncSession, from_day: date, to_day: date
) -> AttendanceSummary:
    """`GET /attendance/summary`: valida el rango y arma las semanas (también las vacías)."""
    check_summary_range(from_day, to_day)
    filas = await summary_rows(session, from_day, to_day, current_clock().now_utc())
    return AttendanceSummary(weeks=weekly_summary(filas, week_starts(from_day, to_day)))


async def member_attendance(
    session: AsyncSession, member_id: UUID, page: PageParams, *, q: str | None = None
) -> Page[AttendanceRowOut]:
    """`GET /members/{id}/attendance`: 404 si no existe; uno dado de baja se ve (N-20)."""
    await members_service.get_ref(session, member_id)
    return await list_attendance(session, AttendanceListQuery(member_id=member_id, q=q), page)
