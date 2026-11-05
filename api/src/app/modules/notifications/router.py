"""Router de plantillas y reglas de aviso (S5-B6, US-120 y US-121). Plano, con la ruta completa en
el decorador (S2-D3).

Admin escribe; admin y coach leen; `member` recibe 403. Las escrituras consumen
`notifications-write`; las lecturas y la vista previa (un POST que no escribe, S5-D216),
`staff-read`. `POST /notification-templates/preview` se registra antes de `/{template_id}`. Las
rutas no hacen `select`: validan, llaman al service y devuelven.
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
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    Channel,
    PreviewIn,
    PreviewOut,
    RuleCreate,
    RuleFilters,
    RuleOut,
    RulePatch,
    TemplateCreate,
    TemplateOut,
    TemplatePatch,
    Trigger,
)

router = APIRouter(
    tags=["notifications"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep


@router.get(
    "/notification-templates", response_model=Page[TemplateOut], responses=responses_for(429)
)
async def list_templates(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
) -> Page[TemplateOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_templates(session, q, page)


@router.post(
    "/notification-templates",
    status_code=201,
    response_model=TemplateOut,
    responses=responses_for(409, 429),
)
async def create_template(
    request: Request, body: TemplateCreate, principal: AdminDep, session: Session
) -> TemplateOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.create_template(session, body)


@router.post(
    "/notification-templates/preview", response_model=PreviewOut, responses=responses_for(429)
)
async def preview_template(request: Request, body: PreviewIn, principal: AdminDep) -> PreviewOut:
    await enforce_user_limit(request, "staff-read", principal.user_id)  # S5-D216: no escribe
    return service.preview(body.subject, body.body)


@router.get(
    "/notification-templates/{template_id}",
    response_model=TemplateOut,
    responses=responses_for(404, 429),
)
async def get_template(
    request: Request, template_id: UUID, principal: StaffDep, session: Session
) -> TemplateOut:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.get_template(session, template_id)


@router.patch(
    "/notification-templates/{template_id}",
    response_model=TemplateOut,
    responses=responses_for(404, 409, 429),
)
async def update_template(
    request: Request,
    template_id: UUID,
    body: TemplatePatch,
    principal: AdminDep,
    session: Session,
) -> TemplateOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.update_template(session, template_id, body)


@router.get("/notification-rules", response_model=Page[RuleOut], responses=responses_for(429))
async def list_rules(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    is_active: bool | None = None,
    channel: Channel | None = None,
    trigger: Trigger | None = None,
) -> Page[RuleOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filters = RuleFilters(q=q, is_active=is_active, channel=channel, trigger=trigger)
    return await service.list_rules(session, filters, page)


@router.post(
    "/notification-rules",
    status_code=201,
    response_model=RuleOut,
    responses=responses_for(409, 429),
)
async def create_rule(
    request: Request, body: RuleCreate, principal: AdminDep, session: Session
) -> RuleOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.create_rule(session, body)


@router.get(
    "/notification-rules/{rule_id}", response_model=RuleOut, responses=responses_for(404, 429)
)
async def get_rule(
    request: Request, rule_id: UUID, principal: StaffDep, session: Session
) -> RuleOut:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.get_rule(session, rule_id)


@router.patch(
    "/notification-rules/{rule_id}", response_model=RuleOut, responses=responses_for(404, 409, 429)
)
async def update_rule(
    request: Request, rule_id: UUID, body: RulePatch, principal: AdminDep, session: Session
) -> RuleOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.update_rule(session, rule_id, body)
