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
Las rutas no hacen `select`: validan, aplican el límite, llaman al service y devuelven.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import StaffDep
from app.modules.memberships import service
from app.modules.memberships.schemas import (
    FreezeIn,
    MembershipOut,
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
