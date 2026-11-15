"""Asistencia y check-in (S7-C1, US-159; S7-D6, S7-D12, S7-D13, S7-D25, S7-D27). Privado del módulo.

- Puerto de membresías (S7-D6, regla 2 bis): `MembershipPort` (`checkin_view` y `lock`),
  `set_membership_port` y `membership_port`. Lo registra `memberships` al importarse (C2); sin
  puerto, `check_in` lanza `MembershipPortNotRegistered` y no escribe nada.
- `check_in(session, data, *, by)`: siempre registra; las banderas reemplazan a los errores. Los
  únicos 409 son `already_checked_in` y `session_cancelled`. Una transacción, en este orden de
  candados (D3 ampliado, `core/locks.py`): socio, sesión (`FOR UPDATE`), membresía (la bloquea el
  puerto) y recién entonces el `INSERT` auditado, que toma la cadena de auditoría:
  1. `members.ensure_exists` (404 a un dado de baja) y `lock_member`; `ensure_exists` otra vez
     (L-4: una baja concurrente no deja asistencia en un socio dado de baja);
  2. `SELECT ... FOR UPDATE` de la sesión (404; `cancelled` da 409): el mismo candado de fila que
     toma la cancelación;
  3. `port.checkin_view(on_date = min(session_date, hoy))`, que bloquea la membresía (S7-D25);
  4. 409 si ya hay asistencia viva del socio; conteo de las vivas de la sesión (las quitadas no
     cuentan);
  5. `checkin_flags` (pura) y `INSERT` dentro de un savepoint que traduce el 23505 del índice
     único parcial a 409 `already_checked_in`;
  6. `MemberCheckedIn` en la misma transacción (memberships descuenta la clase, US-160).
- `list_attendance(...)`: `GET /attendance` (solo asistencias vivas; nombre y apellido por
  `members.service.names_for`, nunca campos cifrados).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.db import violated_constraint
from app.core.locks import lock_member
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import clean_query
from app.core.validators import check_instant_range
from app.modules.classes.events import AttendanceRemoved, MemberCheckedIn
from app.modules.classes.exceptions import (
    AlreadyCheckedIn,
    AttendanceLocked,
    AttendanceNotFound,
    CheckinSessionCancelled,
    ClassValidationError,
    MembershipPortNotRegistered,
    SessionNotFound,
)
from app.modules.classes.models import ATTENDANCE_UNIQUE_ALIVE, Attendance, ClassSession
from app.modules.classes.rules import checkin_flags, checkin_on_date, is_other_day
from app.modules.classes.schemas import (
    AttendanceCreate,
    AttendanceListQuery,
    AttendanceRemove,
    AttendanceRowOut,
    CheckinMembership,
    CheckinOut,
)
from app.modules.members import service as members_service
from app.modules.settings import service as settings_service

logger = logging.getLogger("app.classes")


class MembershipPort(Protocol):
    """Lo que `classes` necesita de `memberships` (S7-D6)."""

    async def checkin_view(
        self, session: AsyncSession, member_id: UUID, *, on_date: date
    ) -> CheckinMembership: ...

    async def lock(self, session: AsyncSession, membership_id: UUID) -> None: ...


_port: MembershipPort | None = None


def set_membership_port(port: MembershipPort | None) -> None:
    """Registra (o quita, con `None`) el puerto; solo lo llama `memberships/service.py`."""
    global _port
    _port = port


def membership_port() -> MembershipPort | None:
    """El puerto registrado, o `None`."""
    return _port


async def alive_attendance_id(
    session: AsyncSession, session_id: UUID, member_id: UUID
) -> UUID | None:
    """La asistencia viva del socio en la sesión, si la hay."""
    return await session.scalar(
        select(Attendance.id).where(
            Attendance.session_id == session_id,
            Attendance.member_id == member_id,
            Attendance.removed_at.is_(None),
        )
    )


async def _alive_count(session: AsyncSession, session_id: UUID) -> int:
    """Asistencias vivas de la sesión (las quitadas no cuentan para el cupo)."""
    total = await session.scalar(
        select(func.count())
        .select_from(Attendance)
        .where(Attendance.session_id == session_id, Attendance.removed_at.is_(None))
    )
    return int(total or 0)


async def _lock_open_session(session: AsyncSession, session_id: UUID) -> ClassSession:
    """La sesión bloqueada `FOR UPDATE` (404; `cancelled` da 409). `populate_existing`: si la
    identidad ya estaba cargada, el estado que dejó una cancelación concurrente manda."""
    clase = await session.scalar(
        select(ClassSession)
        .where(ClassSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if clase is None:
        raise SessionNotFound()
    if clase.status == "cancelled":
        raise CheckinSessionCancelled()
    return clase


async def _insert(session: AsyncSession, fila: Attendance) -> None:
    """El `INSERT` en un savepoint: el 23505 del único parcial es 409 `already_checked_in`."""
    try:
        async with session.begin_nested():
            session.add(fila)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != ATTENDANCE_UNIQUE_ALIVE:
            raise
        raise AlreadyCheckedIn() from None


async def check_in(session: AsyncSession, data: AttendanceCreate, *, by: UUID) -> CheckinOut:
    """Registra la asistencia (docstring del módulo). Nunca bloquea por cupo, hora, día ni
    membresía: devuelve las banderas."""
    port = membership_port()
    if port is None:
        raise MembershipPortNotRegistered("classes: MembershipPort sin registrar")
    await members_service.ensure_exists(session, data.member_id)
    await lock_member(session, data.member_id)
    await members_service.ensure_exists(session, data.member_id)  # L-4
    clase = await _lock_open_session(session, data.session_id)
    reloj = current_clock()
    ahora = reloj.now_utc()
    on_date = checkin_on_date(clase.session_date, reloj.today_bogota())
    vista = await port.checkin_view(session, data.member_id, on_date=on_date)
    if await alive_attendance_id(session, clase.id, data.member_id) is not None:
        raise AlreadyCheckedIn()
    presentes = await _alive_count(session, clase.id)
    ventana = (await settings_service.classes(session)).checkin_window_min
    banderas = checkin_flags(
        vista.status, presentes, clase.capacity, clase.starts_at, ahora, ventana, clase.session_date
    )
    fila = Attendance(
        session_id=clase.id,
        member_id=data.member_id,
        membership_id=vista.membership_id,
        membership_status_at_checkin=vista.status,
        flags=list(banderas),
        checked_in_at=ahora,
        checked_in_by=by,
        created_by=by,
    )
    await _insert(session, fila)
    evento = MemberCheckedIn(
        attendance_id=fila.id,
        session_id=clase.id,
        member_id=data.member_id,
        membership_id=vista.membership_id,
        membership_status=vista.status,
        flags=banderas,
    )
    await events.emit(evento, session)
    logger.info("classes: check-in", extra={"session_id": str(clase.id), "banderas": len(banderas)})
    return CheckinOut(
        id=fila.id,
        flags=list(banderas),
        flagged=bool(banderas),
        membership_status_at_checkin=vista.status,
        attendance_count=presentes + 1,
        capacity=clase.capacity,
    )


async def _lock_alive_attendance(session: AsyncSession, attendance_id: UUID) -> Attendance:
    """La asistencia viva bloqueada `FOR UPDATE` (404 si no existe o ya se quitó).
    `populate_existing`: el estado que dejó un borrado concurrente manda."""
    fila = await session.scalar(
        select(Attendance)
        .where(Attendance.id == attendance_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fila is None or fila.removed_at is not None:
        raise AttendanceNotFound()
    return fila


async def remove_attendance(
    session: AsyncSession,
    attendance_id: UUID,
    data: AttendanceRemove | None,
    *,
    by: UUID,
    role: str,
) -> None:
    """Quita una asistencia: borrado lógico auditado como `update` (US-161, S7-D13, S7-D27 b).

    Una transacción, en este orden de candados (S7-D40, revisión de C2): socio (`lock_member`,
    para que el handler de memberships no corra su `find_overlap` contra una venta paralela del
    mismo socio), asistencia (`FOR UPDATE`; 404 si no existe o ya se quitó), membresía (el
    puerto la bloquea antes de emitir) y recién entonces el `UPDATE` auditado, que toma la
    cadena. El coach solo quita de sesiones de hoy o de ayer en Bogotá (403 `attendance_locked`);
    el admin, de cualquiera, también de una `cancelled`. El motivo (opcional) no viaja en el
    evento: es texto libre (S3-D70)."""
    previa = await session.scalar(
        select(Attendance.member_id).where(Attendance.id == attendance_id)
    )
    if previa is None:
        raise AttendanceNotFound()
    await lock_member(session, previa)
    fila = await _lock_alive_attendance(session, attendance_id)
    reloj = current_clock()
    if role != "admin":  # con la marca de quiosco el router pasa `coach` (revisión de C4, M-2)
        dia = await session.scalar(
            select(ClassSession.session_date).where(ClassSession.id == fila.session_id)
        )
        if dia is None or is_other_day(dia, reloj.today_bogota()):
            raise AttendanceLocked()
    if fila.membership_id is not None:
        port = membership_port()
        if port is None:
            raise MembershipPortNotRegistered("classes: MembershipPort sin registrar")
        await port.lock(session, fila.membership_id)
    fila.removed_at = reloj.now_utc()
    fila.removed_by = by
    fila.removed_reason = data.reason if data is not None else None
    await session.flush()
    evento = AttendanceRemoved(
        attendance_id=fila.id,
        session_id=fila.session_id,
        member_id=fila.member_id,
        membership_id=fila.membership_id,
        membership_status=fila.membership_status_at_checkin,
    )
    await events.emit(evento, session)
    logger.info("classes: asistencia quitada", extra={"session_id": str(fila.session_id)})


def _check_range(query: AttendanceListQuery) -> None:
    """422 con el campo (`from` o `to`) si el rango de `checked_in_at` no es válido."""
    try:
        check_instant_range(
            query.from_at,
            query.to_at,
            now=current_clock().now_utc(),
            field_start="from",
            field_end="to",
        )
    except ValueError as error:
        message = "El rango de fechas no es válido."
        raise ClassValidationError(message=message, field=str(error.args[0])) from None


async def _filtered(
    session: AsyncSession, query: AttendanceListQuery, *, include_deleted: bool = False
) -> Select[Any] | None:
    """La consulta de asistencias vivas con los filtros; `None` si `q` no coincide con nadie."""
    consulta = select(Attendance).where(Attendance.removed_at.is_(None))
    termino = clean_query(query.q)
    if termino:
        # R1b L2: en la ficha de un socio la búsqueda incluye a los dados de baja (N-20); la
        # lista general nunca (revisión de C4, M-3: `include_deleted` solo lo pide la ficha).
        ids = await members_service.search_ids(
            session, termino, include_deleted=include_deleted, name_only=query.name_only
        )
        if not ids:
            return None
        consulta = consulta.where(Attendance.member_id.in_(ids))
    if query.member_id is not None:
        consulta = consulta.where(Attendance.member_id == query.member_id)
    if query.session_id is not None:
        consulta = consulta.where(Attendance.session_id == query.session_id)
    if query.flagged is not None:
        con_banderas = func.cardinality(Attendance.flags) > 0
        consulta = consulta.where(con_banderas if query.flagged else ~con_banderas)
    if query.from_at is not None:
        consulta = consulta.where(Attendance.checked_in_at >= query.from_at)
    if query.to_at is not None:
        consulta = consulta.where(Attendance.checked_in_at < query.to_at)
    return consulta


async def _rows(session: AsyncSession, filas: list[Attendance]) -> list[AttendanceRowOut]:
    """`AttendanceRowOut` de cada fila, con nombre del socio y fecha de la sesión (2 consultas)."""
    nombres = await members_service.names_for(session, [f.member_id for f in filas])
    ids_clase = list({f.session_id for f in filas})
    clases: dict[UUID, ClassSession] = {}
    if ids_clase:
        encontradas = await session.scalars(
            select(ClassSession).where(ClassSession.id.in_(ids_clase))
        )
        clases = {c.id: c for c in encontradas}
    salida: list[AttendanceRowOut] = []
    for f in filas:
        socio = nombres.get(f.member_id)
        clase = clases[f.session_id]
        salida.append(
            AttendanceRowOut(
                id=f.id,
                session_id=f.session_id,
                session_date=clase.session_date,
                session_starts_at=clase.starts_at,
                member_id=f.member_id,
                first_name=socio.first_name if socio else None,
                last_name=socio.last_name if socio else None,
                membership_status_at_checkin=f.membership_status_at_checkin,
                flags=list(f.flags),
                flagged=len(f.flags) > 0,
                checked_in_at=f.checked_in_at,
            )
        )
    return salida


async def list_attendance(
    session: AsyncSession,
    query: AttendanceListQuery,
    page: PageParams,
    *,
    include_deleted: bool = False,
) -> Page[AttendanceRowOut]:
    """`GET /attendance`: asistencias vivas, la más reciente primero (`checked_in_at DESC`);
    `q` busca por socio (`members.service.search_ids`)."""
    _check_range(query)
    consulta = await _filtered(session, query, include_deleted=include_deleted)
    if consulta is None:
        return to_page([], 0, page)
    filas, total = await paginate(
        session, consulta.order_by(Attendance.checked_in_at.desc(), Attendance.id), page
    )
    return to_page(await _rows(session, list(filas)), total, page)
