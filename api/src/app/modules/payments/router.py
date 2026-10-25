"""Router de pagos (S3-B3, US-056; S3-B4, US-095). Plano, con la ruta completa en el decorador
(S2-D3).

- `GET /payments/methods` (admin y coach, `StaffDep`): 200 `PaymentMethodsOut`, un objeto
  `{items}` con los tres medios en orden fijo (D25, S3-C7). Sin límite por usuario (es una lectura,
  S3-D42). Códigos 200, 401 y 403; el 500 y el 503 `busy` los agrega el gancho de OpenAPI.
- `POST /memberships/{membership_id}/payments` (S3-B4, E9, S3-D77; admin y coach, `StaffDep`): 201
  `PaymentOut`. Nace con el gate real (`memberships` lo registra al importarse su `service.py`).
  Límite por usuario `payments-write` (H-2, S3-D42; por defecto 30 por minuto,
  `USER_WRITE_LIMIT_PER_MIN`), contado tras la validación de forma y antes del service. El rol que
  decide la retroactividad de `paid_at` (M-8) sale del principal (`principal.role`), nunca del
  cliente; `confirm_overpayment` y `confirm_duplicate` vienen del cuerpo (S3-D41). Códigos 201,
  401, 403, 404 (`membership_not_found`), 409 (`membership_cancelled`, `payment_exceeds_balance`,
  `payment_possible_duplicate`, `payment_limit_reached`), 422 y 429.
- `POST /payments/{payment_id}/void` (S3-B5, US-097; D13, H-2, S3-D42; solo admin, `AdminDep`):
  200 `PaymentOut` con la fila anulada. Cuerpo `VoidPaymentIn` (`reason`). Límite por usuario
  `admin-write` (por defecto 30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`, E15; compartido con
  anular membresía, B6), contado tras la validación de forma y antes del service. Códigos 200,
  401, 403, 404 (`payment_not_found`), 409 (`payment_already_voided`), 422 (`field="reason"`) y
  429.
- `GET /payments/summary` (S3-B8, US-100; D23, M-4; admin y coach): 200 `PaymentsSummary` del
  mes `month` (`AAAA-MM`, Bogotá; sin `month`, el mes actual). Sin límite por usuario. Códigos
  200, 401, 403 y 422 (`field="month"`).
- `GET /payments` (S3-B8, US-098; D26, M-2, M-4, M-8; admin y coach): `Page[PaymentRow]` con
  `PageParams`, `q` (`SearchQuery`), `from` y `to` (con zona, rango `[from, to)`), `method`,
  `registered_by`, `voided`, `backdated`, `member_id` y `membership_id`. Solo con `q`, la
  cubeta compartida de búsquedas de personas (`PII_SEARCH_BUCKET`, 60 por minuto entre socios,
  membresías y pagos; M-2, S3-D45). Códigos 200, 401, 403, 422 (`validation_error` con
  `field`) y 429.
- `GET /payments/{payment_id}` (S3-B8, US-099; admin y coach): 200 `PaymentDetail`; 404
  `payment_not_found`; 422 si el id no es UUID.
Las rutas fijas (`/payments/summary`, `/payments/methods`) van antes que las de parámetro
(D27): el orden de los `GET` es `summary`, `methods`, lista y `{payment_id}`.
Las rutas no hacen `select`: validan, aplican el límite, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import PII_SEARCH_BUCKET, enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.payments import service
from app.modules.payments.rules import MONTH_LENGTH
from app.modules.payments.schemas import (
    PaymentDetail,
    PaymentIn,
    PaymentListQuery,
    PaymentMethod,
    PaymentMethodsOut,
    PaymentOut,
    PaymentRow,
    PaymentsSummary,
    VoidPaymentIn,
)

router = APIRouter(
    tags=["payments"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/payments/summary", response_model=PaymentsSummary, responses=responses_for(422))
async def payments_summary(
    principal: StaffDep,
    session: SessionDep,
    month: Annotated[str | None, Query(max_length=MONTH_LENGTH)] = None,
) -> PaymentsSummary:
    return await service.summary(session, month=month)


@router.get("/payments/methods", response_model=PaymentMethodsOut, responses=responses_for())
async def payment_methods(principal: StaffDep, session: SessionDep) -> PaymentMethodsOut:
    return await service.methods(session)


@router.get("/payments", response_model=Page[PaymentRow], responses=responses_for(422, 429))
async def list_payments(
    request: Request,
    principal: StaffDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
    method: PaymentMethod | None = None,
    registered_by: UUID | None = None,
    voided: bool | None = None,
    backdated: bool | None = None,
    member_id: UUID | None = None,
    membership_id: UUID | None = None,
) -> Page[PaymentRow]:
    if q:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    filtros = PaymentListQuery(
        q=q,
        from_=from_,
        to=to,
        method=method,
        registered_by=registered_by,
        voided=voided,
        backdated=backdated,
        member_id=member_id,
        membership_id=membership_id,
    )
    return await service.list(session, filtros, page)


@router.get("/payments/{payment_id}", response_model=PaymentDetail, responses=responses_for(404))
async def payment_detail(
    payment_id: UUID, principal: StaffDep, session: SessionDep
) -> PaymentDetail:
    return await service.get(session, payment_id)


@router.post(
    "/memberships/{membership_id}/payments",
    status_code=201,
    response_model=PaymentOut,
    responses=responses_for(404, 409, 422, 429),
)
async def register_payment(
    request: Request,
    membership_id: UUID,
    body: PaymentIn,
    principal: StaffDep,
    session: SessionDep,
) -> PaymentOut:
    await enforce_user_limit(request, "payments-write", principal.user_id)
    return await service.register(
        session,
        membership_id=membership_id,
        amount_cop=body.amount_cop,
        method=body.method,
        reference=body.reference,
        paid_at=body.paid_at,
        confirm_overpayment=body.confirm_overpayment,
        confirm_duplicate=body.confirm_duplicate,
        role=principal.role,
    )


@router.post(
    "/payments/{payment_id}/void",
    response_model=PaymentOut,
    responses=responses_for(404, 409, 422, 429),
)
async def void_payment(
    request: Request,
    payment_id: UUID,
    body: VoidPaymentIn,
    principal: AdminDep,
    session: SessionDep,
) -> PaymentOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.void(session, payment_id=payment_id, reason=body.reason)
