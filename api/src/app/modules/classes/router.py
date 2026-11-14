"""Router de clases (S7-D19, S7-D20). Plano, con la ruta completa en el decorador (S2-D3).

Franjas (S7-A2, US-155), solo admin (el coach recibe 403 también al leer, S7-D19):
- `POST /class-slots`: 201 `SlotOut`; consume `classes-write` (30 por minuto por usuario).
  Códigos 201, 401, 403, 409, 422 y 429.
- `GET /class-slots`: `Page[SlotOut]` con `PageParams`, `q` (nombre), `is_active` y `weekday`;
  consume
  `staff-read`. Códigos 200, 401, 403, 422 y 429.
- `PATCH /class-slots/{slot_id}`: `SlotOut`; `classes-write`. Nunca toca sesiones ya generadas.
  Códigos 200, 401, 403, 404, 409, 422 y 429. No existe `DELETE`: se pausan con `is_active`.
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep
from app.modules.classes import service
from app.modules.classes.schemas import SlotCreate, SlotListQuery, SlotOut, SlotPatch

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
