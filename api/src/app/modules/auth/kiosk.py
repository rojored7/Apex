"""Modo quiosco del lado del servidor (S7-C4, S7-D41; revisión de F4: HIGH-1, MEDIUM-1, MEDIUM-2).
Privado del módulo auth; se usa a través de `auth.service`.

La tablet del check-in queda confinada a una ruta con una marca en la sesión de refresh
(`refresh_tokens.kiosk_path`):
- `enter_kiosk`: fija la marca en la sesión de la cookie y entrega un access con `kiosk=true`
  (con la marca, `core.security.current_user` solo deja pasar `KIOSK_ALLOWED_ROUTES`).
  La rotación del refresh copia la marca (`sessions.refresh`); el logout la borra.
- `exit_kiosk`: verifica la contraseña del usuario con argon2 SIN crear sesión ni rotar el
  refresh y SIN `_register_failure`: un socio frente a la tablet no puede bloquear la cuenta del
  coach. Revisión de C4 (M-1): primero la sesión de la cookie, viva y con marca (sin ella 401
  `invalid_refresh` sin tocar argon2: ni un access robado sirve de oráculo); luego se RESERVA el
  cupo (`EXIT_LIMIT` cada `EXIT_WINDOW_S`, 429) de forma atómica ANTES de verificar, y un acierto
  lo devuelve. La clave es `usuario|inicio de la familia`: cinco fallos en una tablet no bloquean
  al coach en otras. Cada fallo deja una fila de auditoría sin la contraseña.
- S7-D42: con la marca ya puesta, `enter_kiosk` solo acepta el check-in de sesiones programadas de
  hoy o de ayer en Bogotá (403 `kiosk_mode`); sin marca previa entra a cualquier ruta. La fecha y
  el estado llegan por el puerto `set_kiosk_session_info` que registra `classes` (S7-C4c, M-1, L-3).
- `kiosk_path_of`: la marca de la sesión de la cookie para `GET /auth/me`.
Orden de candados igual al de `refresh` (usuario y luego token): la marca y la rotación se
serializan y la marca no se pierde en una carrera.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import actor_scope
from app.core.errors import ForbiddenError
from app.core.security import Principal, TokenInvalid, create_access_token, hash_opaque_token
from app.modules.auth import sessions, tokens
from app.modules.auth.events import KioskEntered, KioskExited, KioskExitFailed
from app.modules.auth.exceptions import (
    InvalidPassword,
    InvalidRefresh,
    KioskSessionInfoNotRegistered,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import AuthPolicy
from app.modules.auth.schemas import KioskSessionOut

logger = logging.getLogger("app.auth")

EXIT_BUCKET: Final = "kiosk-exit-user"
EXIT_LIMIT: Final = 5
EXIT_WINDOW_S: Final = 900
SWITCH_MESSAGE: Final = "Solo puedes pasar al check-in de una clase de hoy o de ayer."

SessionInfo = Callable[[AsyncSession, UUID], Awaitable[tuple[bool, str] | None]]
"""`(en_ventana, status)` de una sesión de clase (`en_ventana`: de hoy o de ayer, regla única de
`classes`), o `None` si no existe."""
_session_info: SessionInfo | None = None


def set_kiosk_session_info(info: SessionInfo | None) -> None:
    """Registra (o quita, con `None`) el puerto que lee la fecha y el estado de una sesión de
    clase (S7-C4c, M-1). Lo llama `classes/service.py` al importarse: `auth` no lee tablas
    ajenas ni importa `classes`."""
    global _session_info
    _session_info = info


def kiosk_session_info_port() -> SessionInfo | None:
    """El puerto registrado, o `None`."""
    return _session_info


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


def _session_id_of(path: str) -> UUID:
    """El id de la ruta `/clases/<uuid>/checkin` (ya validada por `KIOSK_PATH_PATTERN`)."""
    return UUID(path.split("/")[2])


async def _ensure_switchable(session: AsyncSession, path: str) -> None:
    """S7-D42: con la marca puesta, la clase destino debe existir, estar programada (L-3: una
    cancelada no vale) y ser de hoy o de ayer; la lee del puerto de `classes` (M-1)."""
    if _session_info is None:
        raise KioskSessionInfoNotRegistered
    info = await _session_info(session, _session_id_of(path))
    if info is None or info[1] != "scheduled" or not info[0]:
        raise ForbiddenError("kiosk_mode", SWITCH_MESSAGE)


async def enter_kiosk(
    session: AsyncSession,
    principal: Principal,
    token: str | None,
    path: str,
    *,
    policy: AuthPolicy,
) -> KioskSessionOut:
    fila = await _own_session(session, principal, token)
    if fila.kiosk_path is not None:  # cambio de clase dentro del quiosco (S7-D42)
        await _ensure_switchable(session, path)
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
    fila = await _own_session(session, principal, token)  # antes de argon2 (M-1)
    if fila.kiosk_path is None:
        raise InvalidRefresh
    clave = f"{principal.user_id}|{fila.family_started_at}"
    reserva = await ratelimit.reserve(  # atómica y antes de argon2: una ráfaga no la salta
        EXIT_BUCKET, clave, limit=EXIT_LIMIT, window_s=EXIT_WINDOW_S, kind="user"
    )
    usuario = await session.scalar(
        select(User).where(User.id == principal.user_id).execution_options(populate_existing=True)
    )
    if not await sessions.verify_password_or_dummy(usuario, password):
        with actor_scope(principal.user_id):
            await events.emit(KioskExitFailed(user_id=principal.user_id), session)
            await tokens.commit_failure(session)
        logger.info("salida de quiosco rechazada", extra={"user_id": str(principal.user_id)})
        raise InvalidPassword
    await ratelimit.release(EXIT_BUCKET, clave, reserva, kind="user")  # el acierto no cuenta
    with actor_scope(principal.user_id):
        fila.kiosk_path = None
        await session.flush()
        await events.emit(KioskExited(user_id=principal.user_id), session)
    logger.info("quiosco desactivado", extra={"user_id": str(principal.user_id)})
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
