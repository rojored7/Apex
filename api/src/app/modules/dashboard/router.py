"""Router del tablero (S4A-B8; US-108, US-110; S4A-D27, S4A-D29, S4A-D45). Plano (S2-D3).

- `GET /dashboard` (admin y coach, `StaffDep`): `DashboardOut`; mismo cuerpo salvo
  `income_month_cop` (`null` para el coach) y los montos de las frases (S4A-D118).
  Consume `staff-read` (120 por minuto, compartida con `GET /audit`, `GET /audit/{seq}` y
  `GET /members/{member_id}/audit`; S4A-D45, M-1). Sin parámetros: sin 422. Códigos 200, 401,
  403 y 429. `no_store` en el `APIRouter`.
La ruta no hace `select`: aplica el límite, llama al service y devuelve.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import StaffDep
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardOut

router = APIRouter(
    tags=["dashboard"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/dashboard", response_model=DashboardOut, responses=responses_for(429))
async def dashboard(request: Request, principal: StaffDep, session: SessionDep) -> DashboardOut:
    # Literal: `test_user_limits_catalog.py` exige la cubeta como constante (S4A-D45).
    await enforce_user_limit(request, "staff-read", principal.user_id)
    # S4A-D118: el coach recibe el tablero sin ingresos ni montos.
    return await service.summary(session, with_finances=service.can_see_finances(principal.role))
