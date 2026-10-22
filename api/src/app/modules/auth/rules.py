"""Reglas puras de sesión (S2-B2; S2-D4, privado del módulo auth: solo `service.py`,
`tokens.py`, `cookies.py` y `router.py` de auth lo importan; regla `private_helper`).

- `user_status` (S2-D1, precedencia `deleted > locked > inactive > pending_activation >
  active`) y su espejo SQL `status_filter`.
- `account_may_authenticate` y su espejo SQL `AUTH_FILTER` (M-7): el único predicado de
  "esta cuenta puede autenticarse", usado por el cargador, login y refresh. El usuario técnico
  (`SYSTEM_USER_ID`, N-15) queda fuera por id, no solo por `is_active = false`.
- `is_refresh_usable` (vigente, no revocado, familia de menos de `absolute_ttl` y cuenta que
  puede autenticarse), `is_reuse` (rotado y fuera de la gracia de M-2) y `should_auto_lock`
  (S2-D10, H-4: el último admin activo nunca se bloquea).
- `AuthPolicy`: los parámetros de sesión salidos de `Settings` (`cookies.policy_from`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_

from app.core.context import SYSTEM_USER_ID
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.schemas import UserStatus


@dataclass(frozen=True, kw_only=True)
class AuthPolicy:
    """Parámetros de sesión (valores de `Settings`; E5, S2-D10, M-2, M-6, L-4)."""

    access_ttl_s: int
    refresh_ttl: timedelta
    refresh_absolute_ttl: timedelta
    reuse_grace: timedelta
    account_limit: int
    account_window_s: int
    account_global_limit: int
    account_global_window_s: int
    lock_after: int
    min_duration_ms: int


def user_status(user: User) -> UserStatus:
    if user.deleted_at is not None:
        return "deleted"
    if user.locked_at is not None:
        return "locked"
    if not user.is_active:
        return "inactive"
    if user.password_hash is None:
        return "pending_activation"
    return "active"


_VIVO = User.deleted_at.is_(None)
_SIN_BLOQUEO = User.locked_at.is_(None)
_ACTIVO = User.is_active.is_(True)
_CON_HASH = User.password_hash.is_not(None)


def status_filter(status: UserStatus) -> ColumnElement[bool]:
    """Espejo SQL de `user_status`: la misma precedencia, una condición por estado."""
    if status == "deleted":
        return User.deleted_at.is_not(None)
    if status == "locked":
        return and_(_VIVO, User.locked_at.is_not(None))
    if status == "inactive":
        return and_(_VIVO, _SIN_BLOQUEO, User.is_active.is_(False))
    if status == "pending_activation":
        return and_(_VIVO, _SIN_BLOQUEO, _ACTIVO, User.password_hash.is_(None))
    return and_(_VIVO, _SIN_BLOQUEO, _ACTIVO, _CON_HASH)


def account_may_authenticate(user: User) -> bool:
    return user.id != SYSTEM_USER_ID and user_status(user) == "active"


# Espejo SQL de `account_may_authenticate` (M-7).
AUTH_FILTER: ColumnElement[bool] = and_(User.id != SYSTEM_USER_ID, status_filter("active"))


def is_active_admin(user: User) -> bool:
    return user.role == "admin" and account_may_authenticate(user)


def should_auto_lock(failed_count: int, lock_after: int, *, is_last_admin: bool) -> bool:
    return not is_last_admin and failed_count >= lock_after


def is_refresh_usable(
    token: RefreshToken, user: User, now: datetime, *, absolute_ttl: timedelta
) -> bool:
    return (
        token.revoked_at is None
        and now < token.expires_at
        and now < token.family_started_at + absolute_ttl
        and account_may_authenticate(user)
    )


def is_reuse(token: RefreshToken, now: datetime, grace: timedelta) -> bool:
    """Un refresh rotado (con sucesor) usado de nuevo fuera de la gracia. Cerrado por logout
    (sin `replaced_by_id`) nunca es reuso; dentro de la gracia es concurrencia benigna (M-2)."""
    return (
        token.revoked_at is not None
        and token.replaced_by_id is not None
        and now - token.revoked_at >= grace
    )
