"""Router de clases (S7-D19, S7-D20). Plano, con la ruta completa en el decorador (S2-D3).

Franjas (S7-A2, US-155), solo admin (el coach recibe 403 también al leer, S7-D19):
- `POST /class-slots`: 201 `SlotOut`; consume `classes-write` (30 por minuto por usuario).
  Códigos 201, 401, 403, 409, 422 y 429.
- `GET /class-slots`: `Page[SlotOut]` con `PageParams`, `q` (nombre), `is_active` y `weekday`;
  consume
  `staff-read`. Códigos 200, 401, 403, 422 y 429.
- `PATCH /class-slots/{slot_id}`: `SlotOut`; `classes-write`. Nunca toca sesiones ya generadas.
  Códigos 200, 401, 403, 404, 409, 422 y 429. No existe `DELETE`: se pausan con `is_active`.
Sesiones (S7-B2, US-157), admin y coach (`StaffDep`; el socio recibe 403):
- `GET /class-sessions`: `Page[SessionOut]`; `week` (`AAAA-Www`) o `from`/`to` (fechas de Bogotá,
  hasta 62 días), `coach_id` y `status`; `q` (nombre); sin fechas, la semana actual. `staff-read`.
- `POST /class-sessions`: 201 `SessionOut`, sesión extra; `classes-write`. Un coach solo se asigna a
  sí mismo o a nadie (L-3).
- `GET /class-sessions/{session_id}`: `SessionDetail` con asistentes (vacía hasta C1). `staff-read`.
- `POST /class-sessions/{session_id}/cancel`: `SessionOut`; motivo obligatorio; `classes-write`.
- `PATCH /class-sessions/{session_id}` (S8-A4, US-168, N-41): `{wod_id}`; asigna un WOD a la sesión
  o, con `null`, vuelve a heredar el del día; `classes-write`. Códigos 200, 401, 403, 404, 409
  (`session_cancelled`), 422 (`field = "wod_id"`) y 429. `GET /class-sessions?wod_id=` filtra por el
  WOD efectivo.
Asistencia (S7-C1, US-159), admin y coach:
- `POST /attendance`: 201 `CheckinOut`; `attendance-write`. Siempre registra y devuelve `flags`
  (nunca 409 ni 422 por cupo, hora, día o membresía, N-38/N-39); los únicos 409 son
  `already_checked_in` y `session_cancelled`. Códigos 201, 401, 403, 404, 409, 422 y 429.
- `DELETE /attendance/{id}`: 204; cuerpo JSON opcional `{reason}`; `attendance-write`. Borrado
  lógico auditado como `update`; el coach solo de hoy o ayer (403 `attendance_locked`). S7-C3.
- `GET /attendance`: `Page[AttendanceRowOut]` (`member_id`, `session_id`, `flagged`, `from`, `to`
  sobre `checked_in_at`); `staff-read`. Códigos 200, 401, 403, 422 y 429.
- `GET /attendance/summary?from&to`: `AttendanceSummary` (fechas de Bogotá, hasta 26 semanas; 422
  `field = "from"` si `from > to` o el rango pasa de 26 semanas); agrega en SQL; `staff-read`.
  Declarada antes de `/attendance/{id}`. S7-R1, US-162.
- `GET /members/{member_id}/attendance`: `Page[AttendanceRowOut]` de un socio (uno dado de baja
  se ve; 404 si no existe); `staff-read`. S7-R1.
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import AwareDatetime

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import PII_SEARCH_BUCKET, enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.classes import service
from app.modules.classes.exceptions import ClassValidationError
from app.modules.classes.schemas import (
    AttendanceCreate,
    AttendanceListQuery,
    AttendanceRemove,
    AttendanceRowOut,
    AttendanceSummary,
    CancelFutureOut,
    CheckinOut,
    SessionCancel,
    SessionCreate,
    SessionDetail,
    SessionListQuery,
    SessionOut,
    SessionPatch,
    SessionStatus,
    SlotCreate,
    SlotListQuery,
    SlotOut,
    SlotPatch,
)

router = APIRouter(
    tags=["classes"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.post(
    "/class-slots", status_code=201, response_model=SlotOut, responses=responses_for(409, 422, 429)
)
async def create_slot(
    request: Request, body: SlotCreate, principal: AdminDep, session: Session
) -> SlotOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.create_slot(session, body, principal.user_id)


@router.get("/class-slots", response_model=Page[SlotOut], responses=responses_for(422, 429))
async def list_slots(
    request: Request,
    principal: AdminDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    filters: Annotated[SlotListQuery, Depends()],
    q: SearchQuery = None,
) -> Page[SlotOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_slots(session, filters, page, q=q)


@router.patch(
    "/class-slots/{slot_id}",
    response_model=SlotOut,
    responses=responses_for(404, 409, 422, 429),
)
async def update_slot(
    request: Request, slot_id: UUID, body: SlotPatch, principal: AdminDep, session: Session
) -> SlotOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.update_slot(session, slot_id, body, principal.user_id)


@router.post(
    "/class-slots/{slot_id}/cancel-future-sessions",
    response_model=CancelFutureOut,
    responses=responses_for(404, 422, 429),
)
async def cancel_future_sessions(
    request: Request, slot_id: UUID, body: SessionCancel, principal: AdminDep, session: Session
) -> CancelFutureOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.cancel_future_sessions(session, slot_id, body, by=principal.user_id)


@router.get("/class-sessions", response_model=Page[SessionOut], responses=responses_for(422, 429))
async def list_sessions(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    week: Annotated[str | None, Query(max_length=10)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    coach_id: UUID | None = None,
    status: SessionStatus | None = None,
    wod_id: UUID | None = None,
    q: SearchQuery = None,
) -> Page[SessionOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filters = SessionListQuery(
        week=week,
        from_date=date_from,
        to_date=date_to,
        coach_id=coach_id,
        status=status,
        wod_id=wod_id,
    )
    return await service.list_sessions(session, filters, page, q=q)


@router.post(
    "/class-sessions",
    status_code=201,
    response_model=SessionOut,
    responses=responses_for(409, 422, 429),
)
async def create_session(
    request: Request, body: SessionCreate, principal: StaffDep, session: Session
) -> SessionOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.create_extra(session, body, by=principal.user_id, role=principal.role)


@router.get(
    "/class-sessions/{session_id}",
    response_model=SessionDetail,
    responses=responses_for(404, 429),
)
async def get_session(
    request: Request, session_id: UUID, principal: StaffDep, session: Session
) -> SessionDetail:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    if principal.kiosk:  # solo hoy o ayer (S7-D42, V7 M-1)
        await service.ensure_kiosk_session(session, session_id)
    return await service.get_session(session, session_id)


@router.patch(
    "/class-sessions/{session_id}",
    response_model=SessionOut,
    responses=responses_for(404, 409, 422, 429),
)
async def assign_session_wod(
    request: Request,
    session_id: UUID,
    body: SessionPatch,
    principal: StaffDep,
    session: Session,
) -> SessionOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.assign_wod(session, session_id, body, by=principal.user_id)


@router.post(
    "/class-sessions/{session_id}/cancel",
    response_model=SessionOut,
    responses=responses_for(404, 409, 422, 429),
)
async def cancel_session(
    request: Request,
    session_id: UUID,
    body: SessionCancel,
    principal: StaffDep,
    session: Session,
) -> SessionOut:
    await enforce_user_limit(request, "classes-write", principal.user_id)
    return await service.cancel_session(session, session_id, body, by=principal.user_id)


@router.post(
    "/attendance",
    status_code=201,
    response_model=CheckinOut,
    responses=responses_for(404, 409, 422, 429),
)
async def check_in(
    request: Request, body: AttendanceCreate, principal: StaffDep, session: Session
) -> CheckinOut:
    await enforce_user_limit(request, "attendance-write", principal.user_id)
    if principal.kiosk:  # solo hoy o ayer (S7-D42, V7 M-1): una sesión vieja no gasta clases
        await service.ensure_kiosk_session(session, body.session_id)
    return await service.check_in(session, body, by=principal.user_id)


@router.get("/attendance", response_model=Page[AttendanceRowOut], responses=responses_for(422, 429))
async def list_attendance(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    member_id: UUID | None = None,
    session_id: UUID | None = None,
    flagged: bool | None = None,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
    q: SearchQuery = None,
) -> Page[AttendanceRowOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    if q:  # la búsqueda por índice ciego cuesta lo mismo que la de la lista de socios (M-3)
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    if principal.kiosk and session_id is None:  # el quiosco solo ve la clase abierta (M-3)
        raise ClassValidationError(
            message="En modo quiosco indica la sesión (`session_id`).", field="session_id"
        )
    if principal.kiosk and session_id is not None:  # solo hoy o ayer (S7-D42, L-2)
        await service.ensure_kiosk_session(session, session_id)
    filters = AttendanceListQuery(
        member_id=member_id,
        session_id=session_id,
        flagged=flagged,
        from_at=from_,
        to_at=to,
        q=q,
        name_only=principal.kiosk,
    )
    return await service.list_attendance(session, filters, page)


@router.get(
    "/attendance/summary", response_model=AttendanceSummary, responses=responses_for(422, 429)
)
async def attendance_summary(
    request: Request,
    principal: StaffDep,
    session: Session,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> AttendanceSummary:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.attendance_summary(session, date_from, date_to)


@router.get(
    "/members/{member_id}/attendance",
    response_model=Page[AttendanceRowOut],
    responses=responses_for(404, 429),
)
async def member_attendance(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
) -> Page[AttendanceRowOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    if q:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    return await service.member_attendance(session, member_id, page, q=q)


@router.delete(
    "/attendance/{attendance_id}", status_code=204, responses=responses_for(404, 409, 422, 429)
)
async def remove_attendance(
    request: Request,
    attendance_id: UUID,
    principal: StaffDep,
    session: Session,
    body: Annotated[AttendanceRemove | None, Body()] = None,
) -> None:
    await enforce_user_limit(request, "attendance-write", principal.user_id)
    # Un quiosco abierto por un admin no hereda sus poderes: siempre la regla del coach (M-2).
    rol = "coach" if principal.kiosk else principal.role
    await service.remove_attendance(session, attendance_id, body, by=principal.user_id, role=rol)
