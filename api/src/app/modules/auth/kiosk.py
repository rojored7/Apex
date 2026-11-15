"""Modo quiosco del lado del servidor (S7-C4, S7-D41; revisión de F4: HIGH-1, MEDIUM-1, MEDIUM-2).
Privado del módulo auth; se usa a través de `auth.service`.

La tablet del check-in queda confinada a una ruta con una marca en la sesión de refresh
(`refresh_tokens.kiosk_path`):
- `enter_kiosk`: fija la marca en la sesión de la cookie y entrega un access con `kiosk=true`
  (con la marca, `core.security.current_user` solo deja pasar `KIOSK_ALLOWED_ROUTES`).
  La rotación del refresh copia la marca (`sessions.refresh`); el logout la borra.
- `exit_kiosk`: verifica la contraseña del usuario con argon2 SIN crear sesión ni rotar el
  refresh y SIN `_register_failure`: un socio frente a la tablet no puede bloquear la cuenta del
  coach. Los fallos tienen su tope por usuario (`EXIT_LIMIT` cada `EXIT_WINDOW_S`, 429) y
  dejan una fila de auditoría sin la contraseña.
- `kiosk_path_of`: la marca de la sesión de la cookie para `GET /auth/me`.
Orden de candados igual al de `refresh` (usuario y luego token): la marca y la rotación se
serializan y la marca no se pierde en una carrera.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import actor_scope
from app.core.security import Principal, TokenInvalid, create_access_token, hash_opaque_token
from app.modules.auth import sessions, tokens
from app.modules.auth.events import KioskEntered, KioskExited, KioskExitFailed
from app.modules.auth.exceptions import InvalidPassword, InvalidRefresh
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import AuthPolicy
from app.modules.auth.schemas import KioskSessionOut

logger = logging.getLogger("app.auth")

EXIT_BUCKET: Final = "kiosk-exit-user"
EXIT_LIMIT: Final = 5
EXIT_WINDOW_S: Final = 900


def _usable(fila: RefreshToken, user_id: UUID, now: datetime) -> bool:
    return fila.user_id == user_id and fila.revoked_at is None and fila.expires_at > now


async def _own_session(
    session: AsyncSession, principal: Principal, token: str | None
) -> RefreshToken:
    """La fila de la cookie, bloqueada, si es del usuario y está viva; si no, `InvalidRefresh`."""
    encontrado = await sessions.locked_refresh_and_owner(session, token)
    now = current_clock().now_utc()
    if encontrado is None or not _usable(encontrado[0], principal.user_id, now):
        raise InvalidRefresh
    return encontrado[0]


def _out(principal: Principal, policy: AuthPolicy, path: str | None) -> KioskSessionOut:
    acceso = create_access_token(
        principal.user_id,
        principal.role,
        principal.member_id,
        current_clock(),
        kiosk=path is not None,
    )
    return KioskSessionOut(access_token=acceso, expires_in=policy.access_ttl_s, kiosk_path=path)


async def enter_kiosk(
    session: AsyncSession,
    principal: Principal,
    token: str | None,
    path: str,
    *,
    policy: AuthPolicy,
) -> KioskSessionOut:
    fila = await _own_session(session, principal, token)
    with actor_scope(principal.user_id):
        fila.kiosk_path = path
        await session.flush()
        await events.emit(KioskEntered(user_id=principal.user_id, path=path), session)
    logger.info("quiosco activado", extra={"user_id": str(principal.user_id)})
    return _out(principal, policy, path)


async def exit_kiosk(
    session: AsyncSession,
    principal: Principal,
    token: str | None,
    password: str,
    *,
    policy: AuthPolicy,
) -> KioskSessionOut:
    clave = str(principal.user_id)
    await ratelimit.enforce(  # antes de argon2 y sin sumar: solo cuentan los fallos
        EXIT_BUCKET, clave, limit=EXIT_LIMIT, window_s=EXIT_WINDOW_S, kind="user", count=False
    )
    usuario = await session.scalar(
        select(User).where(User.id == principal.user_id).execution_options(populate_existing=True)
    )
    if not await sessions.verify_password_or_dummy(usuario, password):
        await ratelimit.record(EXIT_BUCKET, clave, window_s=EXIT_WINDOW_S, kind="user")
        with actor_scope(principal.user_id):
            await events.emit(KioskExitFailed(user_id=principal.user_id), session)
            await tokens.commit_failure(session)
        logger.info("salida de quiosco rechazada", extra={"user_id": clave})
        raise InvalidPassword
    fila = await _own_session(session, principal, token)
    with actor_scope(principal.user_id):
        fila.kiosk_path = None
        await session.flush()
        await events.emit(KioskExited(user_id=principal.user_id), session)
    logger.info("quiosco desactivado", extra={"user_id": clave})
    return _out(principal, policy, None)


async def kiosk_path_of(session: AsyncSession, user_id: UUID, token: str | None) -> str | None:
    """La marca de la sesión viva de la cookie (propia del usuario) o `None`."""
    if not token:
        return None
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    ahora = current_clock().now_utc()
    return await session.scalar(
        select(RefreshToken.kiosk_path).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > ahora,
        )
    )
