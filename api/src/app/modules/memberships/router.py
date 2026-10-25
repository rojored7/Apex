"""Router de membresías (S3-B1, US-084). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members/{member_id}/memberships` (admin y coach, `StaffDep`): 201 `SellMembershipOut`.
  Límite por usuario `memberships-write` (H-2, S3-D42; por defecto 30 por minuto,
  `USER_WRITE_LIMIT_PER_MIN`): la venta 31 en un minuto del mismo usuario da 429. Códigos 201,
  401, 403, 404 (`member_not_found`), 409 (`membership_conflict`, `membership_overlap`), 422 y
  429; el 500 y el 503 `busy` los agrega el gancho de OpenAPI. Con `first_payment` (S3-B4, D4)
  el pago se registra en la misma unidad con el rol del principal (`principal.role`, nunca un
  valor del cliente; M-8) y sus errores llevan `field="first_payment.<campo>"` (E5). La venta con
  pago gasta además la cubeta `payments-write` (revisión de seguridad de B4, H-2): con esa
  cubeta agotada la venta con pago da 429 y la venta sin pago sigue.
- `POST /memberships/{membership_id}/freeze` (S3-B2, US-089; admin y coach por Q7, `StaffDep`):
  200 `MembershipOut`. Comparte la cubeta `memberships-write` con la venta (S3-D42): 20 ventas y
  11 congelaciones del mismo usuario en un minuto dan 429 en la 31. Códigos 200, 401, 403, 404
  (`membership_not_found`), 409 (`membership_not_freezable`, `freeze_already_scheduled`,
  `freeze_limit_reached`, `freeze_days_exceeded`, `overlaps_future_membership`), 422
  (`validation_error` con `field="frozen_to"`, `freeze_too_retroactive`,
  `freeze_outside_validity`) y 429 (D14).
- `POST /members/{member_id}/memberships` con `renew: true` (S3-B6, US-088; Q1): la misma ruta y
  la misma cubeta `memberships-write`; el `start_date` del cuerpo se descarta. 409
  `future_membership_exists` con `existing_id` si ya hay una futura.
- `GET /members/{member_id}/memberships/renewal-preview?plan_id=` (S3-B6, US-088; admin y coach,
  `StaffDep`): 200 `RenewalPreviewOut`. Es una lectura: sin límite por usuario (S3-D42) y sin
  candados. Códigos 200, 401, 403, 404 (`member_not_found`), 409 (`future_membership_exists`) y
  422 (`plan_id` ausente o no UUID, `plan_invalid`, `plan_inactive`, `member_inactive`).
- `POST /memberships/{membership_id}/cancel` (S3-B6, US-090; solo admin, `AdminDep`): 200
  `MembershipOut` con la membresía anulada. Cuerpo `CancelMembershipIn` (`reason`). Límite por
  usuario `admin-write` (por defecto 30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`, E15),
  compartido con anular un pago (S3-B5), contado tras la validación de forma y antes del service.
  Códigos 200, 401, 403, 404 (`membership_not_found`), 409 (`membership_already_cancelled`), 422
  (`validation_error` con `field="reason"`) y 429.
- `GET /memberships/summary` (S3-B7, US-092; admin y coach, `StaffDep`): 200
  `MembershipSummaryOut` (cinco enteros: socios no dados de baja por estado resuelto; caché de 30
  s, S3-D53). Declarada ANTES de `/memberships/{membership_id}`: si no, "summary" se leería como
  un id y daría 422. Sin límite por usuario.
- `GET /memberships` (S3-B7, US-091; admin y coach): `Page[MembershipRow]` con `PageParams`,
  `status` separado por comas (hasta 100 caracteres, L-9), `q` (`SearchQuery`), `plan_id`,
  `member_id` (UUID), `ends_from` y `ends_to`. Solo con `q`, la cubeta compartida de búsquedas
  de personas (`PII_SEARCH_BUCKET`, 60 por minuto entre socios, membresías y pagos; M-2,
  S3-D45). Códigos 200, 401, 403, 422 (`validation_error` con `field`) y 429.
- `GET /memberships/{membership_id}` (S3-B7; admin y coach): 200 `MembershipOut` con sus
  congelaciones; 404 `membership_not_found`; 422 si el id no es UUID.
Las rutas no hacen `select`: validan, aplican el límite, llaman al service y devuelven.
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
from app.core.ratelimit import PII_SEARCH_BUCKET, enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.memberships import service
from app.modules.memberships.schemas import (
    STATUS_FILTER_MAX_LENGTH,
    CancelMembershipIn,
    FreezeIn,
    MembershipListQuery,
    MembershipOut,
    MembershipRow,
    MembershipSummaryOut,
    RenewalPreviewOut,
    SellMembershipIn,
    SellMembershipOut,
)

router = APIRouter(
    tags=["memberships"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.post(
    "/members/{member_id}/memberships",
    status_code=201,
    response_model=SellMembershipOut,
    responses=responses_for(404, 409, 429),
)
async def sell_membership(
    request: Request,
    member_id: UUID,
    body: SellMembershipIn,
    principal: StaffDep,
    session: SessionDep,
) -> SellMembershipOut:
    await enforce_user_limit(request, "memberships-write", principal.user_id)
    if body.first_payment is not None:
        await enforce_user_limit(request, "payments-write", principal.user_id)
    return await service.sell(
        session,
        member_id=member_id,
        plan_id=body.plan_id,
        start_date=body.start_date,
        renew=body.renew,
        first_payment=body.first_payment,
        role=principal.role,
    )


@router.post(
    "/memberships/{membership_id}/freeze",
    response_model=MembershipOut,
    responses=responses_for(404, 409, 422, 429),
)
async def freeze_membership(
    request: Request,
    membership_id: UUID,
    body: FreezeIn,
    principal: StaffDep,
    session: SessionDep,
) -> MembershipOut:
    await enforce_user_limit(request, "memberships-write", principal.user_id)
    return await service.freeze(
        session,
        membership_id=membership_id,
        frozen_from=body.frozen_from,
        frozen_to=body.frozen_to,
    )


@router.get(
    "/members/{member_id}/memberships/renewal-preview",
    response_model=RenewalPreviewOut,
    responses=responses_for(404, 409, 422),
)
async def renewal_preview(
    member_id: UUID, plan_id: UUID, principal: StaffDep, session: SessionDep
) -> RenewalPreviewOut:
    return await service.renewal_preview(session, member_id=member_id, plan_id=plan_id)


@router.post(
    "/memberships/{membership_id}/cancel",
    response_model=MembershipOut,
    responses=responses_for(404, 409, 422, 429),
)
async def cancel_membership(
    request: Request,
    membership_id: UUID,
    body: CancelMembershipIn,
    principal: AdminDep,
    session: SessionDep,
) -> MembershipOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.cancel(session, membership_id=membership_id, reason=body.reason)


@router.get("/memberships/summary", response_model=MembershipSummaryOut)
async def membership_summary(principal: StaffDep, session: SessionDep) -> MembershipSummaryOut:
    return await service.summary(session)


@router.get("/memberships", response_model=Page[MembershipRow], responses=responses_for(422, 429))
async def list_memberships(
    request: Request,
    principal: StaffDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    membership_status: Annotated[
        str | None, Query(alias="status", max_length=STATUS_FILTER_MAX_LENGTH)
    ] = None,
    plan_id: UUID | None = None,
    member_id: UUID | None = None,
    ends_from: date | None = None,
    ends_to: date | None = None,
) -> Page[MembershipRow]:
    if q:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    filtros = MembershipListQuery(
        status=membership_status,
        q=q,
        plan_id=plan_id,
        member_id=member_id,
        ends_from=ends_from,
        ends_to=ends_to,
    )
    return await service.list(session, filtros, page)


@router.get(
    "/memberships/{membership_id}", response_model=MembershipOut, responses=responses_for(404)
)
async def membership_detail(
    membership_id: UUID, principal: StaffDep, session: SessionDep
) -> MembershipOut:
    return await service.get(session, membership_id)
