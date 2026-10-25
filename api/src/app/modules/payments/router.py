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
Las rutas fijas (`/payments/methods`, `/payments/summary`) van antes que las de parámetro (D27).
Las rutas no hacen `select`: validan, aplican el límite, llaman al service y devuelven.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.payments import service
from app.modules.payments.schemas import PaymentIn, PaymentMethodsOut, PaymentOut, VoidPaymentIn

router = APIRouter(
    tags=["payments"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/payments/methods", response_model=PaymentMethodsOut, responses=responses_for())
async def payment_methods(principal: StaffDep, session: SessionDep) -> PaymentMethodsOut:
    return await service.methods(session)


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
