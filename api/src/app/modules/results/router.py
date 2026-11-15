"""Router de `results` (S8-B1, US-169). Plano, con la ruta completa en el decorador (S2-D3).

- `PUT /results`: registra (o corrige, con `supersedes_id`) el resultado de un socio en un WOD;
  admin y coach (`StaffDep`; el socio recibe 403); `results-write` (30 por minuto por usuario).
  201 `ResultOut`. Códigos 201, 401, 403, 404, 409, 422 y 429. El origen (`source`) es `desk`: la
  tablet de quiosco llega en B3 (S8-D31).
La ruta no hace `select`: valida, llama al service y devuelve.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import StaffDep
from app.modules.results import service
from app.modules.results.schemas import ResultIn, ResultOut

router = APIRouter(
    tags=["results"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep


@router.put(
    "/results",
    status_code=201,
    response_model=ResultOut,
    responses=responses_for(404, 409, 422, 429),
)
async def put_result(
    request: Request, body: ResultIn, principal: StaffDep, session: Session
) -> ResultOut:
    await enforce_user_limit(request, "results-write", principal.user_id)
    return await service.record_result(session, body, by=principal.user_id, source="desk")
