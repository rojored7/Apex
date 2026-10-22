"""Router de prueba para `require_role` y `current_user` (US-034 T7). Solo en tests."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import current_actor
from app.core.security import AdminDep, Principal, StaffDep, require_role

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


@router.get("/pendiente")
async def pendiente(
    principal: Annotated[
        Principal,
        Depends(require_role("admin", "coach", "member", allow_pending_password=True)),
    ],
) -> dict[str, bool]:
    """Como `GET /auth/me`: admite una cuenta que debe cambiar la contraseña (M-8, S2-B3)."""
    return {"must_change_password": principal.must_change_password}


# S3-W0-2 (S3-D59, D-2): los alias comunes de rol que usan los routers nuevos.
@router.get("/staff-dep")
async def staff_dep(principal: StaffDep) -> dict[str, str]:
    return {"user_id": str(principal.user_id), "role": principal.role}


@router.get("/admin-dep")
async def admin_dep(principal: AdminDep) -> dict[str, str]:
    return {"user_id": str(principal.user_id), "role": principal.role}
