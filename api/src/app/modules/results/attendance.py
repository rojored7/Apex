"""Asistencia de una clase con el resultado vigente de cada socio (S8-B3, US-169 CA1, S8-D14).
Privado del módulo `results`.

Compone `classes.get_session` (asistentes vivos con nombre y apellido: ningún campo cifrado), el WOD
efectivo de la sesión (`wods.get_wod`) y los resultados vigentes de los socios de la página en UNA
consulta. En quiosco la clase debe ser de hoy o de ayer (S8-D15, 403 `kiosk_mode`).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.classes import service as classes_service
from app.modules.classes.schemas import SessionOut
from app.modules.results.models import WodResult
from app.modules.results.schemas import AttendanceResultRow, ResultOut, SessionAttendanceOut
from app.modules.wods import service as wods_service


async def _current_by_member(
    session: AsyncSession, wod_id: UUID | None, member_ids: list[UUID]
) -> dict[UUID, ResultOut]:
    if wod_id is None or not member_ids:
        return {}
    filas = await session.scalars(
        select(WodResult).where(
            WodResult.wod_id == wod_id,
            WodResult.member_id.in_(member_ids),
            WodResult.is_current.is_(True),
        )
    )
    return {f.member_id: ResultOut.model_validate(f) for f in filas.all()}


async def session_attendance(
    session: AsyncSession, session_id: UUID, page: PageParams, *, kiosk: bool = False
) -> SessionAttendanceOut:
    if kiosk:
        await classes_service.ensure_kiosk_session(session, session_id)
    detalle = await classes_service.get_session(session, session_id)
    wod = (
        await wods_service.get_wod(session, detalle.effective_wod_id)
        if detalle.effective_wod_id is not None
        else None
    )
    asistentes = detalle.attendees[page.offset : page.offset + page.limit]
    vigentes = await _current_by_member(
        session, detalle.effective_wod_id, [a.member_id for a in asistentes]
    )
    items = [
        AttendanceResultRow(
            member_id=a.member_id,
            first_name=a.first_name,
            last_name=a.last_name,
            has_result=a.member_id in vigentes,
            result=vigentes.get(a.member_id),
        )
        for a in asistentes
    ]
    sesion = detalle.model_dump(exclude={"attendees"})
    return SessionAttendanceOut(
        session=SessionOut(**sesion),
        wod=wod,
        items=items,
        total=len(detalle.attendees),
        limit=page.limit,
        offset=page.offset,
    )
