"""Router de pagos (S3-B3, US-056). Plano, con la ruta completa en el decorador (S2-D3).

- `GET /payments/methods` (admin y coach, `StaffDep`): 200 `PaymentMethodsOut`, un objeto
  `{items}` con los tres medios en orden fijo (D25, S3-C7). Sin límite por usuario (es una lectura,
  S3-D42). Códigos 200, 401 y 403; el 500 y el 503 `busy` los agrega el gancho de OpenAPI.
- `POST /memberships/{membership_id}/payments` NO se publica en B3: nace en B4 con el gate real
  (E9, S3-D77); sin él respondería 500 `MembershipGateNotRegistered`.
Las rutas fijas (`/payments/methods`, `/payments/summary`) van antes que las de parámetro (D27).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.security import StaffDep
from app.modules.payments import service
from app.modules.payments.schemas import PaymentMethodsOut

router = APIRouter(
    tags=["payments"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/payments/methods", response_model=PaymentMethodsOut, responses=responses_for())
async def payment_methods(principal: StaffDep, session: SessionDep) -> PaymentMethodsOut:
    return await service.methods(session)
