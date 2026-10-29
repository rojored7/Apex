"""Router del módulo `audit` (S4A-B3, US-104; S4A-D14, S4A-D47). Plano, con la ruta completa en el
decorador (S2-D3).

- `GET /audit/verify/last` (admin, `AdminDep`): 200 `VerifyResultOut | null` (nunca 404). Sin
  límite por usuario (lee una fila, M-1) y sin parámetros (sin 422). Se registra antes de
  `GET /audit/{seq}` (S4A-B4).
- `POST /audit/verify` (admin, `AdminDep`): consume `audit-verify` (3 por minuto) y
  `audit-verify-hour` (20 por hora) por usuario (M-3, S4A-D47). 200 `VerifyResultOut` (hasta
  `SYNC_VERIFY_MAX_ROWS` filas), 202 `VerifyStartedOut` (segundo plano; la respuesta lleva
  `Cache-Control: no-store` a mano porque es un `JSONResponse`), 409 `verification_running`,
  429. Sin cuerpo: sin 422.
Las rutas no hacen `select`: aplican el límite, llaman al service y devuelven.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import NO_STORE, no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep
from app.modules.audit import service
from app.modules.audit.schemas import VerifyResultOut, VerifyStartedOut

router = APIRouter(
    tags=["audit"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/audit/verify/last", response_model=VerifyResultOut | None)
async def last_verification(principal: AdminDep, session: SessionDep) -> VerifyResultOut | None:
    vista = await service.last_verification(session)
    return None if vista is None else VerifyResultOut.model_validate(vista, from_attributes=True)


@router.post(
    "/audit/verify",
    response_model=VerifyResultOut,
    responses={
        **responses_for(409, 429),
        202: {"model": VerifyStartedOut, "description": "La verificación sigue en segundo plano."},
    },
)
async def verify_chain(
    request: Request, principal: AdminDep, session: SessionDep
) -> VerifyResultOut | JSONResponse:
    await enforce_user_limit(request, "audit-verify", principal.user_id)
    await enforce_user_limit(request, "audit-verify-hour", principal.user_id)
    salida = await service.verify(session, by=principal.user_id)
    if isinstance(salida, service.Started):
        last = (
            None
            if salida.last is None
            else VerifyResultOut.model_validate(salida.last, from_attributes=True)
        )
        cuerpo = VerifyStartedOut(last=last).model_dump(mode="json")
        return JSONResponse(status_code=202, content=cuerpo, headers={"Cache-Control": NO_STORE})
    return VerifyResultOut.model_validate(salida.result, from_attributes=True)
