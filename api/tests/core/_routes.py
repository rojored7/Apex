"""Router de prueba para `require_role` y `current_user` (US-034 T7). Solo en tests."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import current_actor
from app.core.security import Principal, require_role

router = APIRouter(prefix="/_t")


@router.get("/admin")
async def solo_admin(
    principal: Annotated[Principal, Depends(require_role("admin"))],
) -> dict[str, str]:
    return {"user_id": str(principal.user_id), "role": principal.role}


@router.get("/staff")
async def staff(
    principal: Annotated[Principal, Depends(require_role("admin", "coach"))],
) -> dict[str, str]:
    return {"user_id": str(principal.user_id), "role": principal.role}


@router.get("/actor")
async def actor(
    principal: Annotated[Principal, Depends(require_role("admin", "coach", "member"))],
) -> dict[str, str | None]:
    valor = current_actor.get()
    return {
        "actor": str(valor) if valor else None,
        "member_id": str(principal.member_id) if principal.member_id else None,
    }
