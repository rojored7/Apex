"""Router de membresías (S3-B1, US-084). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members/{member_id}/memberships` (admin y coach, `StaffDep`): 201 `SellMembershipOut`.
  Límite por usuario `memberships-write` (H-2, S3-D42; por defecto 30 por minuto,
  `USER_WRITE_LIMIT_PER_MIN`): la venta 31 en un minuto del mismo usuario da 429. Códigos 201,
  401, 403, 404 (`member_not_found`), 409 (`membership_conflict`, `membership_overlap`), 422 y
  429; el 500 y el 503 `busy` los agrega el gancho de OpenAPI.
La ruta no hace `select`: valida, aplica el límite, llama al service y devuelve.
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
from app.modules.memberships.schemas import SellMembershipIn, SellMembershipOut

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
    return await service.sell(
        session,
        member_id=member_id,
        plan_id=body.plan_id,
        start_date=body.start_date,
        renew=body.renew,
        first_payment=body.first_payment,
    )
