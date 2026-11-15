"""Router de `wods` (S8-A1, US-165). Plano, con la ruta completa en el decorador (S2-D3).

Movimientos, admin y coach (`StaffDep`; el socio recibe 403):
- `GET /movements`: `Page[CatalogMovementOut]` con `PageParams`, `q`, `category` y `active`;
  `staff-read`. Códigos 200, 401, 403, 422 y 429.
- `POST /movements`: 201 `CatalogMovementOut`; `wods-write` (30 por minuto por usuario). Códigos
  201, 401, 403, 409, 422 y 429.
- `PATCH /movements/{movement_id}`: `CatalogMovementOut`; `wods-write`. Códigos 200, 401, 403, 404,
  409, 422 y 429. No existe `DELETE`: se desactivan con `is_active`.
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
from app.core.security import StaffDep
from app.modules.wods import service
from app.modules.wods.schemas import (
    CatalogMovementOut,
    MovementCreate,
    MovementListQuery,
    MovementPatch,
)

router = APIRouter(
    tags=["wods"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.get(
    "/movements", response_model=Page[CatalogMovementOut], responses=responses_for(422, 429)
)
async def list_movements(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    filters: Annotated[MovementListQuery, Depends()],
    q: SearchQuery = None,
) -> Page[CatalogMovementOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_movements(session, filters, page, q=q)


@router.post(
    "/movements",
    status_code=201,
    response_model=CatalogMovementOut,
    responses=responses_for(409, 422, 429),
)
async def create_movement(
    request: Request, body: MovementCreate, principal: StaffDep, session: Session
) -> CatalogMovementOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.create_movement(session, body, principal.user_id)


@router.patch(
    "/movements/{movement_id}",
    response_model=CatalogMovementOut,
    responses=responses_for(404, 409, 422, 429),
)
async def update_movement(
    request: Request,
    movement_id: UUID,
    body: MovementPatch,
    principal: StaffDep,
    session: Session,
) -> CatalogMovementOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.update_movement(session, movement_id, body, principal.user_id)
