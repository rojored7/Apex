"""Fábrica de `auth.users` (S2-B1). `make_one_time_token` llega en S2-B3."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import hash_password
from app.modules.auth.models import User

DOMINIO_PRUEBA = "test.apex"


async def make_user(
    session: AsyncSession,
    *,
    role: str = "coach",
    email: str | None = None,
    password: str | None = None,
    member_id: UUID | None = None,
    is_active: bool = True,
    locked_at: datetime | None = None,
    **cambios: Any,
) -> User:
    """Inserta un `User` bajo `SYSTEM_USER_ID` y confirma. Sin `password` queda sin hash.

    El correo por defecto es único y del dominio `@test.apex` (la limpieza de S2-B2 lo usa).
    Un `member` sin `member_id` recibe uno nuevo (CHECK `member_id_for_member`).
    """
    if role == "member" and member_id is None:
        member_id = uuid4()
    hashed = await anyio.to_thread.run_sync(hash_password, password) if password else None
    valores: dict[str, Any] = {
        "email": email or f"u-{uuid4().hex[:12]}@{DOMINIO_PRUEBA}",
        "password_hash": hashed,
        "role": role,
        "member_id": member_id,
        "is_active": is_active,
        "locked_at": locked_at,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    usuario = User(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(usuario)
        await session.flush()
        await session.commit()
    return usuario
