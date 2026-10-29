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

S4A-B4 (US-102, US-103; S4A-D16, S4A-D17): la lectura vive en los privados `queries.py` y
`diff.py`; la fachada expone `AUDITABLE_TABLES`, `AuditFilters`, `build_audit_filters`,
`list_entries(session, query, page)` (arma los filtros con `current_clock()` y llama a
`queries.list`) y `get_entry(session, seq)` (`queries.get`).

S4A-B5 (US-106; S4A-D20): re-exporta `member_history(session, member_id, page, q)` de
`queries.py`; la ruta vive en `members/router.py` (arista `members -> audit`), no aquí.

S4A-B8 (US-110; S4A-D28, S4A-D51): re-exporta `recent(session, tables, limit, *, actions,
exclude_user_ids)` de `queries.py` y las constantes `RECENT_TABLES_ALLOWED`,
`AUDIT_TABLES_EXCLUDED_FROM_RECENT` y `MAX_RECENT_LIMIT`, más `AuditEntryView`; los lee el
tablero (arista `dashboard -> audit`).

Los handlers se suscriben al importarse este módulo (`main.load_module_services()` lo importa
en el api y en el CLI); `events.subscribe` es idempotente, así que cada uno queda una vez.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.audit import record
from app.core.clock import current_clock
from app.core.pagination import Page, PageParams
from app.modules.audit import queries
from app.modules.audit.queries import (
    AUDIT_TABLES_EXCLUDED_FROM_RECENT,
    AUDITABLE_TABLES,
    MAX_RECENT_LIMIT,
    RECENT_TABLES_ALLOWED,
    AuditFilters,
    build_audit_filters,
    member_history,
    recent,
)
from app.modules.audit.schemas import AuditDetail, AuditEntryView, AuditListQuery, AuditRow
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
    "AUDITABLE_TABLES",
    "AUDIT_TABLES_EXCLUDED_FROM_RECENT",
    "MAX_RECENT_LIMIT",
    "RECENT_TABLES_ALLOWED",
    "AuditEntryView",
    "AuditFilters",
    "Finished",
    "Started",
    "acquire_verify_lock",
    "build_audit_filters",
    "cancel_background_verifications",
    "get_entry",
    "last_verification",
    "list_entries",
    "member_history",
    "on_login_attempted",
    "on_password_changed",
    "on_sessions_revoked",
    "on_user_locked",
    "recent",
    "release_verify_lock",
    "verify",
]

USERS_TABLE: Final = "auth.users"


async def list_entries(
    session: AsyncSession, query: AuditListQuery, page: PageParams
) -> Page[AuditRow]:
    """`GET /audit` (US-102): filtros validados contra el reloj de la app y la página."""
    filtros = build_audit_filters(query, page, now=current_clock().now_utc())
    return await queries.list(session, filtros, page)


async def get_entry(session: AsyncSession, seq: int) -> AuditDetail:
    """`GET /audit/{seq}` (US-103): el detalle con el diff y sin blobs."""
    return await queries.get(session, seq)


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
