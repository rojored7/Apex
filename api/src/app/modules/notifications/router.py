"""Router de plantillas y reglas de aviso (S5-B6, US-120 y US-121). Plano, con la ruta completa en
el decorador (S2-D3).

Admin escribe; admin y coach leen; `member` recibe 403. Las escrituras consumen
`notifications-write`; las lecturas y la vista previa (un POST que no escribe, S5-D216),
`staff-read`. `POST /notification-templates/preview` se registra antes de `/{template_id}`. Las
rutas no hacen `select`: validan, llaman al service y devuelven.

S5-B7: avisos (`/notifications/today`, `/notifications`, `/notifications/{id}`, `POST .../wa-link`,
`POST .../skip` y `/members/{id}/notifications`), para admin y coach.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.clock import current_clock
from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import PII_SEARCH_BUCKET, enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    Channel,
    NotificationFilters,
    NotificationOut,
    PreviewIn,
    PreviewOut,
    RuleCreate,
    RuleFilters,
    RuleOut,
    RulePatch,
    SkipIn,
    Status,
    TemplateCreate,
    TemplateOut,
    TemplatePatch,
    Trigger,
    WaLinkOut,
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


# Avisos (S5-B7, US-124, US-127 a US-130) ---------------------------------------------------------
# `/notifications/today` se registra antes de `/notifications/{notification_id}`. Admin y coach;
# `member` recibe 403. Lecturas: `staff-read` (y `members-search` si llega `q`, que busca por
# nombre de socio); `skip`: `notifications-write`; `wa-link`: las tres ventanas de `members-reveal`
# (descifra un teléfono).


async def _limitar_busqueda(request: Request, user_id: UUID, q: str | None) -> None:
    if q is not None:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, user_id)


@router.get(
    "/notifications/today", response_model=Page[NotificationOut], responses=responses_for(429)
)
async def list_today(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
) -> Page[NotificationOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    await _limitar_busqueda(request, principal.user_id, q)
    return await service.today_list(session, current_clock().today_bogota(), page, q)


@router.get("/notifications", response_model=Page[NotificationOut], responses=responses_for(429))
async def list_notifications(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    status: Status | None = None,
    channel: Channel | None = None,
    rule_id: UUID | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> Page[NotificationOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    await _limitar_busqueda(request, principal.user_id, q)
    filters = NotificationFilters(
        q=q,
        status=status,
        channel=channel,
        rule_id=rule_id,
        from_date=from_date,
        to_date=to_date,
    )
    return await service.list(session, filters, page)


@router.get(
    "/notifications/{notification_id}",
    response_model=NotificationOut,
    responses=responses_for(404, 429),
)
async def get_notification(
    request: Request, notification_id: UUID, principal: StaffDep, session: Session
) -> NotificationOut:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.get(session, notification_id)


@router.post(
    "/notifications/{notification_id}/wa-link",
    response_model=WaLinkOut,
    responses=responses_for(400, 404, 409, 422, 429),
)
async def notification_wa_link(
    request: Request, notification_id: UUID, principal: StaffDep, session: Session
) -> WaLinkOut:
    # Literales: `test_user_limits_catalog.py` exige el bucket como constante en la llamada.
    await enforce_user_limit(request, "members-reveal", principal.user_id)
    await enforce_user_limit(request, "members-reveal-hour", principal.user_id)
    await enforce_user_limit(request, "members-reveal-day", principal.user_id)
    return await service.wa_link(session, notification_id, principal.user_id)


@router.post(
    "/notifications/{notification_id}/skip",
    response_model=NotificationOut,
    responses=responses_for(404, 409, 422, 429),
)
async def skip_notification(
    request: Request,
    notification_id: UUID,
    body: SkipIn,
    principal: StaffDep,
    session: Session,
) -> NotificationOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.skip(session, notification_id, body.reason, principal.user_id)


@router.get(
    "/members/{member_id}/notifications",
    response_model=Page[NotificationOut],
    responses=responses_for(404, 429),
)
async def list_member_notifications(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,  # regla de datos 6: toda lista acepta q; esta la ignora
) -> Page[NotificationOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_for_member(session, member_id, page)
