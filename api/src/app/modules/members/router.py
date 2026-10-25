"""Router de socios (S2-B7, US-069; L-1). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members` (admin y coach): 201 `MemberDetailOut` enmascarado. Límite por usuario
  autenticado (`enforce_user_limit(request, "members-write", user_id)`, L-1; por defecto 60 altas
  por minuto, `USER_MEMBERS_WRITE_LIMIT_PER_MIN`); el alta 61 da 429. Códigos 201, 401, 403,
  409, 422 y 429.
- `GET /members` (admin y coach; S2-B8, US-070): `Page[MemberRowOut]` con `PageParams`, `q`
  (`SearchQuery`, hasta 100; nunca se registra), `status` y `sort`. Solo cuando hay `q`, límite
  por usuario de búsquedas (`PII_SEARCH_BUCKET`, por defecto 60 por minuto,
  `USER_SEARCH_LIMIT_PER_MIN`; L-1); sin `q` no cuenta. S3-B9b (US-071, D22): `membership_status`
  y `plan_id` (422 con `field`; un plan inexistente da la lista vacía). Códigos 200, 401, 403,
  422 y 429.
- `GET /members/{member_id}` (admin y coach, también sobre un dado de baja, N-20; S3-B9b,
  US-073): `MemberDetailOut` con los cinco campos enmascarados (D20). Límite por usuario
  `members-detail` (M-2, S3-D45; por defecto 120 por minuto, `USER_DETAIL_LIMIT_PER_MIN`).
  Códigos 200, 401, 403, 404, 422 y 429.
El 429 se declara por ruta, nunca en el `APIRouter` (D27, E2). Las rutas no hacen `select`:
validan, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import PII_SEARCH_BUCKET, enforce_user_limit
from app.core.security import StaffDep
from app.modules.members import service
from app.modules.members.schemas import (
    DEFAULT_MEMBER_SORT,
    MemberCreate,
    MemberDetailOut,
    MemberListQuery,
    MemberRowOut,
    MembershipFilterStatus,
    MemberSort,
    MemberStatusFilter,
)

# M6: datos de personas (nombres y máscaras): ninguna respuesta se guarda en caché.
router = APIRouter(
    tags=["members"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.post(
    "/members",
    status_code=201,
    response_model=MemberDetailOut,
    responses=responses_for(409, 429),
)
async def create_member(
    request: Request, body: MemberCreate, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-write", principal.user_id)
    return await service.create(session, body)


@router.get("/members", response_model=Page[MemberRowOut], responses=responses_for(429))
async def list_members(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    member_status: Annotated[MemberStatusFilter | None, Query(alias="status")] = None,
    sort: MemberSort = DEFAULT_MEMBER_SORT,
    membership_status: MembershipFilterStatus | None = None,
    plan_id: UUID | None = None,
) -> Page[MemberRowOut]:
    if q:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    filtros = MemberListQuery(
        q=q,
        status=member_status,
        sort=sort,
        membership_status=membership_status,
        plan_id=plan_id,
    )
    return await service.list(session, filtros, page)


@router.get(
    "/members/{member_id}",
    response_model=MemberDetailOut,
    responses=responses_for(404, 422, 429),
)
async def get_member(
    request: Request, member_id: UUID, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-detail", principal.user_id)
    return await service.get(session, member_id)
