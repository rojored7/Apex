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
S3-B10 (US-074, US-075, US-076; D19, D21, M-1, M-3, S3-D44, S3-D46):
- `POST /members/{member_id}/reveal` (admin y coach): `RevealOut` en claro de un campo cifrado.
  Tres ventanas por usuario: `members-reveal` (30 por minuto), `members-reveal-hour` (200 por
  hora) y `members-reveal-day` (600 por día). La IP de `client_ip` va a la auditoría (L-12).
  Códigos 200, 401, 403, 404, 422 y 429. Al pasar de la mitad del cupo horario (la 101 de 200)
  registra `logger.warning("reveal volume", extra={"user_id", "count"})` (S3-D44, M-1).
- `PATCH /members/{member_id}` (admin y coach): `MemberDetailOut` enmascarado; consume
  `members-write` (compartido con `POST /members`). Códigos 200, 401, 403, 404, 409, 422 y 429.
- `DELETE /members/{member_id}` (solo admin): 204. Códigos 204, 401, 403, 404, 409, 422 y 429.
- `POST /members/{member_id}/reactivate` (solo admin): `MemberDetailOut`. Códigos 200, 401, 403,
  404, 409, 422 y 429.
- Las dos consumen `admin-write` (30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`; L1 de la
  revisión de Fase 4 del Sprint 3), la cubeta de anular un pago y anular una membresía.
S4A-B5 (US-106; S4A-D20, S4A-D45):
- `GET /members/{member_id}/audit` (admin y coach, también sobre un dado de baja):
  `Page[MemberHistoryItem]` con `PageParams` y `q`; consume `staff-read` (120 por minuto,
  compartida con `GET /audit`, `GET /audit/{seq}` y el tablero). Códigos 200, 401, 403, 404, 422
  (`offset` mayor que 100.000 con `field="offset"`) y 429.
El 429 se declara por ruta, nunca en el `APIRouter` (D27, E2). Las rutas no hacen `select`:
validan, llaman al service y devuelven.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import (
    PII_SEARCH_BUCKET,
    USER_LIMITS,
    client_ip,
    enforce_user_limit,
    usage,
)
from app.core.security import AdminDep, StaffDep
from app.modules.audit.schemas import MemberHistoryItem
from app.modules.members import service
from app.modules.members.schemas import (
    DEFAULT_MEMBER_SORT,
    MemberCreate,
    MemberDetailOut,
    MemberListQuery,
    MemberPatch,
    MemberRowOut,
    MembershipFilterStatus,
    MemberSort,
    MemberStatusFilter,
    RevealIn,
    RevealOut,
)

# M6: datos de personas (nombres y máscaras): ninguna respuesta se guarda en caché.
router = APIRouter(
    tags=["members"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api

logger = logging.getLogger("app.members")

REVEAL_HOUR_BUCKET = "members-reveal-hour"  # la ventana del aviso `reveal volume` (S3-D44)


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


@router.get(
    "/members/{member_id}/audit",
    response_model=Page[MemberHistoryItem],
    responses=responses_for(404, 422, 429),
)
async def member_history(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
) -> Page[MemberHistoryItem]:
    # Literal: `test_user_limits_catalog.py` exige la cubeta como constante (S4A-D45).
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.history(session, member_id, page, q)


def _ip(request: Request) -> str:
    redes: Sequence[IPv4Network | IPv6Network] = getattr(request.app.state, "trusted_proxies", ())
    return client_ip(request, redes)


async def _avisar_volumen_de_reveal(request: Request, user_id: UUID) -> None:
    """S3-D44 (M-1): `reveal volume` cuando el usuario pasa de la mitad de su cupo horario. El
    conteo incluye la petición actual (con un tope de 200, la 101 avisa y la 100 no); el registro
    lleva el usuario y el conteo, nunca el socio ni el valor."""
    topes: Mapping[str, tuple[int, int]] = getattr(request.app.state, "user_limits", USER_LIMITS)
    tope, ventana = topes[REVEAL_HOUR_BUCKET]
    conteo = await usage(REVEAL_HOUR_BUCKET, str(user_id), window_s=ventana)
    if conteo * 2 > tope:
        logger.warning("reveal volume", extra={"user_id": str(user_id), "count": conteo})


@router.post(
    "/members/{member_id}/reveal",
    response_model=RevealOut,
    responses=responses_for(404, 422, 429),
)
async def reveal_member_field(
    request: Request, member_id: UUID, body: RevealIn, principal: StaffDep, session: Session
) -> RevealOut:
    # Literales: `test_user_limits_catalog.py` exige el bucket como constante en la llamada.
    await enforce_user_limit(request, "members-reveal", principal.user_id)
    await enforce_user_limit(request, "members-reveal-hour", principal.user_id)
    await enforce_user_limit(request, "members-reveal-day", principal.user_id)
    await _avisar_volumen_de_reveal(request, principal.user_id)
    return await service.reveal(session, member_id, body.field, ip=_ip(request))


@router.patch(
    "/members/{member_id}",
    response_model=MemberDetailOut,
    responses=responses_for(403, 404, 409, 422, 429),
)
async def update_member(
    request: Request, member_id: UUID, body: MemberPatch, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-write", principal.user_id)
    return await service.update(session, member_id, body, role=principal.role)


@router.delete(
    "/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(404, 409, 422, 429),
)
async def deactivate_member(
    request: Request, member_id: UUID, principal: AdminDep, session: Session
) -> None:
    # Sin `Response` propia: FastAPI arma el 204 con las cabeceras de `no_store`.
    await enforce_user_limit(request, "admin-write", principal.user_id)
    await service.deactivate(session, member_id)


@router.post(
    "/members/{member_id}/reactivate",
    response_model=MemberDetailOut,
    responses=responses_for(404, 409, 422, 429),
)
async def reactivate_member(
    request: Request, member_id: UUID, principal: AdminDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.reactivate(session, member_id)
