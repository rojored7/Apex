"""Suscriptores de auditoría de los eventos de seguridad de `auth` (S2-B6; US-107; S2-D43,
S2-D49, L-8 y L-13).

Cada handler escribe una fila en `audit.audit_log` con `core.audit.record`, dentro de la
transacción del emisor: si falla, el bloqueo, la revocación o el cambio se revierten.
`audit` importa de `auth.service` solo las clases de evento; `auth` no importa nada de `audit`.
`after` nunca lleva correos tecleados, contraseñas, hashes ni tokens: cada handler arma su
`after` con una lista cerrada de campos del evento, nunca con el evento entero.

Las filas de `UserLocked`, `SessionsRevoked` y `PasswordChanged` son `update` sobre
`auth.users` con `after.event`; el hook ORM (US-016) deja además su propio `update` de las
columnas auditadas (dos filas por bloqueo, a propósito; blueprint 7.5).

S4A-B3 (S4A-D18): la fachada re-exporta la verificación de la cadena del privado `verify.py`
(`verify`, `last_verification`, `cancel_background_verifications`, `Finished`, `Started` y el
candado `acquire_verify_lock`/`release_verify_lock`, que también usa `verify-audit` del CLI).

Los handlers se suscriben al importarse este módulo (`main.load_module_services()` lo importa
en el api y en el CLI); `events.subscribe` es idempotente, así que cada uno queda una vez.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.audit import record
from app.modules.audit.verify import (
    Finished,
    Started,
    acquire_verify_lock,
    cancel_background_verifications,
    last_verification,
    release_verify_lock,
    verify,
)
from app.modules.auth.service import (
    LoginAttempted,
    PasswordChanged,
    SessionsRevoked,
    UserLocked,
)

__all__ = [
    "Finished",
    "Started",
    "acquire_verify_lock",
    "cancel_background_verifications",
    "last_verification",
    "on_login_attempted",
    "on_password_changed",
    "on_sessions_revoked",
    "on_user_locked",
    "release_verify_lock",
    "verify",
]

USERS_TABLE: Final = "auth.users"


async def on_login_attempted(event: LoginAttempted, session: AsyncSession) -> None:
    """Fila `login` sobre `auth.users` del propio usuario: `result`, `reason`, `ip` y
    `user_agent` (L-8), nunca el correo tecleado (N-31)."""
    await record(
        session,
        action="login",
        table_name=USERS_TABLE,
        record_id=event.user_id,
        before=None,
        after={
            "result": event.result,
            "reason": event.reason,
            "ip": event.ip,
            "user_agent": event.user_agent,
        },
        user_id=event.user_id,
    )


async def on_user_locked(event: UserLocked, session: AsyncSession) -> None:
    """Fila `update` con `after = {"event": "UserLocked", "reason": ...}` atribuida a `by`."""
    await record(
        session,
        action="update",
        table_name=USERS_TABLE,
        record_id=event.user_id,
        before=None,
        after={"event": "UserLocked", "reason": event.reason},
        user_id=event.by,
    )


async def on_sessions_revoked(event: SessionsRevoked, session: AsyncSession) -> None:
    """Fila `update` con `after = {"event": "SessionsRevoked", "reason": ..., "revoked": n}`
    atribuida a `by` (`SYSTEM_USER_ID` en el reuso y en el bloqueo automático; S2-D49)."""
    await record(
        session,
        action="update",
        table_name=USERS_TABLE,
        record_id=event.user_id,
        before=None,
        after={"event": "SessionsRevoked", "reason": event.reason, "revoked": event.revoked},
        user_id=event.by,
    )


async def on_password_changed(event: PasswordChanged, session: AsyncSession) -> None:
    """Fila `update` con `after = {"event": "PasswordChanged", "via": ...,
    "via_link_issued_by": ...}` atribuida a `by` (L-13; manda sobre el blueprint 7.5)."""
    emisor = event.via_link_issued_by
    await record(
        session,
        action="update",
        table_name=USERS_TABLE,
        record_id=event.user_id,
        before=None,
        after={
            "event": "PasswordChanged",
            "via": event.via,
            "via_link_issued_by": str(emisor) if emisor is not None else None,
        },
        user_id=event.by,
    )


events.subscribe(LoginAttempted, on_login_attempted)
events.subscribe(UserLocked, on_user_locked)
events.subscribe(SessionsRevoked, on_sessions_revoked)
events.subscribe(PasswordChanged, on_password_changed)
