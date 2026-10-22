"""Ayudas de las pruebas del ciclo de vida del usuario (S2-B5; US-049, US-050, US-051).

- `ruta(user_id, accion=None)`: `/api/v1/users/{id}` y sus acciones (`lock`, `unlock`,
  `revoke-sessions`).
- `entrar(session, usuario)`: un login real por el service (una sesión más) con commit;
  devuelve el refresh en claro.
- `sesiones_vivas(session, user_id, now)`: refresh no revocados y vigentes, leídos de la base.
- `como(admin)`: el actor que pondría `current_user` (la auditoría lo exige en el flush).
- `EVENTOS_DE_CUENTA`: los eventos de dominio de auth, para probar que algo no emite ninguno.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.auth import service
from app.modules.auth.models import RefreshToken
from app.modules.auth.service import (
    LoginAttempted,
    PasswordChanged,
    SessionsRevoked,
    UserCreated,
    UserLocked,
)
from tests.auth._sesion import IP_A, politica
from tests.conftest import CLAVE_PRUEBA, UsuarioPrueba

USERS = "/api/v1/users"
EVENTOS_DE_CUENTA = (UserCreated, UserLocked, SessionsRevoked, PasswordChanged, LoginAttempted)


def ruta(user_id: object, accion: str | None = None) -> str:
    base = f"{USERS}/{user_id}"
    return f"{base}/{accion}" if accion else base


def como(usuario: UsuarioPrueba | UUID) -> AbstractContextManager[None]:
    quien = usuario if isinstance(usuario, UUID) else usuario.id
    return actor_scope(quien)


async def entrar(session: AsyncSession, usuario: UsuarioPrueba) -> str:
    resultado = await service.login(
        session, usuario.email, CLAVE_PRUEBA, ip=IP_A, user_agent="pytest", policy=politica()
    )
    await session.commit()
    return resultado.refresh_token


async def sesiones_vivas(session: AsyncSession, user_id: UUID, now: datetime) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    return int(total or 0)
