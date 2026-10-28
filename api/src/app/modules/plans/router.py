"""Router de planes (S2-B9, US-078 y US-079; S2-D26). Plano, con la ruta completa en el
decorador (S2-D3).

- `POST /plans` (solo admin): 201 `PlanOut`; consume `admin-write` (30 por minuto por usuario, la
  cubeta de las demás escrituras de solo admin; M-A de V10, S3-D100). Códigos 201, 401, 403,
  409, 422 y 429.
- `GET /plans` (admin y coach): `Page[PlanOut]` con `PageParams`, `q` (`SearchQuery`, nunca se
  registra) y `active`. El alcance lo aplica el service: el coach solo con `active=true`
  (`active=false` o sin parámetro: 403). Códigos 200, 401, 403 y 422.
- `GET /plans/{plan_id}` (admin y coach): `PlanOut`; un plan inactivo da 403 al coach; uno dado
  de baja o inexistente, 404. Códigos 200, 401, 403, 404 y 422.
`PATCH`, `activate`, `deactivate` y `DELETE` entran en el Sprint 4A. Las rutas no hacen
`select`: validan, llaman al service y devuelven.
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
from app.core.security import AdminDep, StaffDep
from app.modules.plans import service
from app.modules.plans.schemas import PlanCreate, PlanOut

router = APIRouter(  # M6 y M7
    tags=["plans"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.post("/plans", status_code=201, response_model=PlanOut, responses=responses_for(409, 429))
async def create_plan(
    request: Request, body: PlanCreate, principal: AdminDep, session: Session
) -> PlanOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.create(session, body)


@router.get("/plans", response_model=Page[PlanOut])
async def list_plans(
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    active: bool | None = None,
) -> Page[PlanOut]:
    return await service.list(session, q=q, active=active, page=page, role=principal.role)


@router.get("/plans/{plan_id}", response_model=PlanOut, responses=responses_for(404))
async def get_plan(plan_id: UUID, principal: StaffDep, session: Session) -> PlanOut:
    return await service.detail(session, plan_id, role=principal.role)
