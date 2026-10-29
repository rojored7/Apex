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
S4A-B7 (US-080, US-081, US-082; S4A-D22 a D26), solo admin y con `admin-write` (compartida con
`POST /plans`), el 429 declarado por ruta:
- `PATCH /plans/{plan_id}`: `PlanOut`. Códigos 200, 401, 403, 404, 409, 422 y 429.
- `POST /plans/{plan_id}/activate` y `/deactivate`: `PlanOut`, idempotentes. Códigos 200, 401,
  403, 404, 422 y 429.
- `DELETE /plans/{plan_id}`: 204 sin cuerpo; 409 `plan_has_active_memberships` con el conteo.
  Códigos 204, 401, 403, 404, 409, 422 y 429.
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.plans import service
from app.modules.plans.schemas import PlanCreate, PlanOut, PlanPatch

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


@router.patch(
    "/plans/{plan_id}", response_model=PlanOut, responses=responses_for(404, 409, 422, 429)
)
async def update_plan(
    request: Request, plan_id: UUID, body: PlanPatch, principal: AdminDep, session: Session
) -> PlanOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update(session, plan_id, body)


@router.post(
    "/plans/{plan_id}/activate", response_model=PlanOut, responses=responses_for(404, 422, 429)
)
async def activate_plan(
    request: Request, plan_id: UUID, principal: AdminDep, session: Session
) -> PlanOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.set_active(session, plan_id, True)


@router.post(
    "/plans/{plan_id}/deactivate", response_model=PlanOut, responses=responses_for(404, 422, 429)
)
async def deactivate_plan(
    request: Request, plan_id: UUID, principal: AdminDep, session: Session
) -> PlanOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.set_active(session, plan_id, False)


@router.delete(
    "/plans/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(404, 409, 422, 429),
)
async def delete_plan(
    request: Request, plan_id: UUID, principal: AdminDep, session: Session
) -> None:
    # Sin `Response` propia: FastAPI arma el 204 con las cabeceras de `no_store`.
    await enforce_user_limit(request, "admin-write", principal.user_id)
    await service.deactivate_or_fail(session, plan_id)
