"""Fábricas de `auth.users` (S2-B1) y `auth.one_time_tokens` (S2-B3, `make_one_time_token`)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import hash_opaque_token, hash_password, new_opaque_token
from app.modules.auth.models import OneTimeToken, User

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


class _ConId(Protocol):
    @property
    def id(self) -> UUID: ...


async def make_one_time_token(
    session: AsyncSession,
    user: _ConId,
    purpose: str,
    *,
    expires_in: timedelta,
    used_at: datetime | None = None,
    created_by: UUID = SYSTEM_USER_ID,
) -> tuple[str, OneTimeToken]:
    """Inserta un token de un solo uso (solo su hash) y confirma; devuelve `(claro, fila)`.

    `expires_at = reloj de la app + expires_in` (un `expires_in` negativo deja uno vencido).
    `user` es un `User` o un `UsuarioPrueba` (basta `.id`). No pasa por
    `issue_one_time_token`: así las pruebas de ese caso de uso tienen datos previos propios.
    """
    claro = new_opaque_token()
    fila = OneTimeToken(
        user_id=user.id,
        token_hash=hash_opaque_token(claro),
        purpose=purpose,
        expires_at=current_clock().now_utc() + expires_in,
        used_at=used_at,
        created_by=created_by,
    )
    with actor_scope(created_by):
        session.add(fila)
        await session.flush()
        await session.commit()
    return claro, fila
