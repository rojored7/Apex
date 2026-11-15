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
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.classes import service
from app.modules.classes.schemas import (
    CancelFutureOut,
    SessionCancel,
    SessionCreate,
    SessionDetail,
    SessionListQuery,
    SessionOut,
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
    q: SearchQuery = None,
) -> Page[SessionOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filters = SessionListQuery(
        week=week, from_date=date_from, to_date=date_to, coach_id=coach_id, status=status
    )
    return await service.list_sessions(session, filters, page, q=q)


@router.post(
    "/class-sessions",
    status_code=201,
    response_model=SessionOut,
    responses=responses_for(422, 429),
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
    return await service.get_session(session, session_id)


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
