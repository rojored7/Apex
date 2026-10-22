"""Router de socios (S2-B7, US-069; L-1). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members` (admin y coach): 201 `MemberDetailOut` enmascarado. Límite por usuario
  autenticado de 60 altas por minuto (`ratelimit.enforce("members-write", user_id, limit=60,
  window_s=60)`, L-1); el alta 61 da 429. Códigos 201, 401, 403, 409, 422 y 429.
La ruta no hace `select`: valida el cuerpo, llama al service y devuelve.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.db import get_session
from app.core.security import Principal, require_role
from app.modules.members import service
from app.modules.members.schemas import MemberCreate, MemberDetailOut

router = APIRouter(tags=["members"])

MEMBERS_WRITE_BUCKET: Final = "members-write"
MEMBERS_WRITE_LIMIT: Final = 60
MEMBERS_WRITE_WINDOW_S: Final = 60

Staff = Annotated[Principal, Depends(require_role("admin", "coach"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/members", status_code=201, response_model=MemberDetailOut)
async def create_member(body: MemberCreate, principal: Staff, session: Session) -> MemberDetailOut:
    await ratelimit.enforce(
        MEMBERS_WRITE_BUCKET,
        str(principal.user_id),
        limit=MEMBERS_WRITE_LIMIT,
        window_s=MEMBERS_WRITE_WINDOW_S,
        kind="user",
    )
    return await service.create(session, body)
