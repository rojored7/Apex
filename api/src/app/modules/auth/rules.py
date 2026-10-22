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

S2-B3 (US-045, US-046, US-047):
- `validate_password_policy(password, *, current_hash=None, field="password")`: la política de
  `core.security` (L-5: `too_long` en 129, `too_short`, `too_common`) traducida a `AuthError`
  422 `weak_password` con el `field` pedido (`new_password` en cambio y reset); con
  `current_hash`, la nueva debe ser distinta de la actual.
- `activation_url(base_url, token)`: `<FRONT_BASE_URL>/restablecer/<token>` (blueprint 7.2);
  `ACTIVATE_TTL` (72 h) y `RESET_TTL` (1 h).
- `escape_like(q)`: escapa `\\`, `%` y `_` para `ILIKE ... ESCAPE '\'`.
- `user_row(user, *, active_sessions)` y `user_out(user)`: las salidas con `status` calculado
  por `user_status`; nunca llevan `password_hash`.

S2-B4 (US-048, US-052): `is_one_time_token_usable(token, user, now)` (S2-D40) y
`link_purpose_for(user)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from sqlalchemy import ColumnElement, and_

from app.core.context import SYSTEM_USER_ID
from app.core.security import WeakPasswordError, verify_password
from app.core.security import validate_password_policy as core_password_policy
from app.modules.auth.exceptions import AuthError
from app.modules.auth.models import OneTimeToken, RefreshToken, User
from app.modules.auth.schemas import UserOut, UserRow, UserStatus

ACTIVATE_TTL: Final = timedelta(hours=72)
RESET_TTL: Final = timedelta(hours=1)
RESET_PATH: Final = "/restablecer/"


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


# S2-B3 · contraseñas, enlaces y salidas ------------------------------------------------


def validate_password_policy(
    password: str, *, current_hash: str | None = None, field: str = "password"
) -> None:
    """N-10 y L-5: `too_long` (129), `too_short`, `too_common`, en ese orden, y luego (con
    `current_hash`) distinta de la actual. La igualdad cuesta un argon2: solo se revisa si la
    longitud y la lista ya pasaron. El mensaje nunca repite la contraseña."""
    try:
        core_password_policy(password)
    except WeakPasswordError as error:
        raise AuthError(
            "weak_password", "La contraseña es demasiado débil.", field=field
        ) from error
    if current_hash is not None and verify_password(current_hash, password):
        raise AuthError(
            "weak_password", "La contraseña nueva debe ser distinta de la actual.", field=field
        )


def activation_url(base_url: str, token: str) -> str:
    """`<base sin barras finales>/restablecer/<token>`; el token es base64url y no se escapa."""
    return f"{base_url.rstrip('/')}{RESET_PATH}{token}"


LIKE_ESCAPE: Final = "\\"


def escape_like(value: str) -> str:
    """Escapa la barra invertida (primero), `%` y `_` para `ILIKE ... ESCAPE '\\'`."""
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def user_row(user: User, *, active_sessions: int) -> UserRow:
    return UserRow(
        id=user.id,
        email=user.email,
        role=user.role,
        status=user_status(user),
        member_id=user.member_id,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        active_sessions=active_sessions,
    )


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        member_id=user.member_id,
        status=user_status(user),
        must_change_password=user.must_change_password,
    )


# S2-B4 · enlaces de un solo uso (US-048, US-052) ------------------------------------------

# `account_may_authenticate` sin la exigencia de hash: los dos estados que un `activate` admite.
_MAY_ACTIVATE: Final[frozenset[UserStatus]] = frozenset({"active", "pending_activation"})


def is_one_time_token_usable(token: OneTimeToken, user: User, now: datetime) -> bool:
    """S2-D40: sin usar, `expires_at > now` y `account_may_authenticate(user)`, salvo la
    exigencia de hash cuando el propósito es `activate` (un pendiente solo activa)."""
    if token.used_at is not None or not now < token.expires_at:
        return False
    if token.purpose == "activate":
        return user.id != SYSTEM_USER_ID and user_status(user) in _MAY_ACTIVATE
    return account_may_authenticate(user)


def link_purpose_for(user: User) -> Literal["activate", "reset"]:
    """`activate` si la cuenta no tiene hash; si no, `reset` (blueprint S2-B4)."""
    return "activate" if user.password_hash is None else "reset"
