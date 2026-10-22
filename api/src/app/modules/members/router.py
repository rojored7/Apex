"""Router de socios (S2-B7, US-069; L-1). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members` (admin y coach): 201 `MemberDetailOut` enmascarado. Límite por usuario
  autenticado de 60 altas por minuto (`ratelimit.enforce("members-write", user_id, limit=60,
  window_s=60)`, L-1); el alta 61 da 429. Códigos 201, 401, 403, 409, 422 y 429.
- `GET /members` (admin y coach; S2-B8, US-070): `Page[MemberRowOut]` con `PageParams`, `q`
  (`SearchQuery`, hasta 100; nunca se registra), `status` y `sort`. Solo cuando hay `q`, límite
  por usuario de 60 búsquedas por minuto (`members-search`, L-1); sin `q` no cuenta. Códigos
  200, 401, 403, 422 y 429.
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query

from app.core import ratelimit
from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.security import Principal, require_role
from app.modules.members import service
from app.modules.members.schemas import (
    DEFAULT_MEMBER_SORT,
    MemberCreate,
    MemberDetailOut,
    MemberListQuery,
    MemberRowOut,
    MemberSort,
    MemberStatusFilter,
)

# M6: datos de personas (nombres y máscaras): ninguna respuesta se guarda en caché.
router = APIRouter(
    tags=["members"], dependencies=[Depends(no_store)], responses=responses_for(401, 403, 429)
)

MEMBERS_WRITE_BUCKET: Final = "members-write"
MEMBERS_WRITE_LIMIT: Final = 60
MEMBERS_WRITE_WINDOW_S: Final = 60
MEMBERS_SEARCH_BUCKET: Final = "members-search"
MEMBERS_SEARCH_LIMIT: Final = 60
MEMBERS_SEARCH_WINDOW_S: Final = 60

Staff = Annotated[Principal, Depends(require_role("admin", "coach"))]
Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.post(
    "/members", status_code=201, response_model=MemberDetailOut, responses=responses_for(409)
)
async def create_member(body: MemberCreate, principal: Staff, session: Session) -> MemberDetailOut:
    await ratelimit.enforce(
        MEMBERS_WRITE_BUCKET,
        str(principal.user_id),
        limit=MEMBERS_WRITE_LIMIT,
        window_s=MEMBERS_WRITE_WINDOW_S,
        kind="user",
    )
    return await service.create(session, body)


@router.get("/members", response_model=Page[MemberRowOut])
async def list_members(
    principal: Staff,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    member_status: Annotated[MemberStatusFilter | None, Query(alias="status")] = None,
    sort: MemberSort = DEFAULT_MEMBER_SORT,
) -> Page[MemberRowOut]:
    if q:
        await ratelimit.enforce(
            MEMBERS_SEARCH_BUCKET,
            str(principal.user_id),
            limit=MEMBERS_SEARCH_LIMIT,
            window_s=MEMBERS_SEARCH_WINDOW_S,
            kind="user",
        )
    filtros = MemberListQuery(q=q, status=member_status, sort=sort)
    return await service.list(session, filtros, page)
