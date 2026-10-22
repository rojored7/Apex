"""Service de auth (US-041; adaptador del puerto `PrincipalLoader` de US-034; S2-B2 US-042,
US-043 y US-044).

- Puras: `validate_user_role` (S7: `member` exige `member_id`; `admin`/`coach` no lo llevan
  en v0.1), `normalize_login_email`, `validate_password_policy` (delegada a `core.security`,
  traducida a `AuthError` 422). `user_status` e `is_active_admin` viven en `rules.py` (M-7) y
  se reexportan aquí.
- `seed_admin(force_change=True)`: crea el primer admin activo si no hay otro (el usuario
  técnico no cuenta), con `must_change_password` (M-8), audita sin el hash y emite `UserCreated`.
- `load_active_principal`: el cargador real de `current_user`, con `rules.AUTH_FILTER` (M-7);
  trae `must_change_password` y `tokens_valid_after` (H-3). Se registra al importarse el módulo.
- `names_for`, `ids_by_email`, `active_user_id_by_email`: lecturas para auditoría (US-110) y
  para `--as <email>` del CLI (N-15; solo cuentas en estado `active`, L-4 del Sprint 1).
- `login` (blueprint 7.1 corregido por H-4 y M-6): límite por cuenta con clave
  `"{correo}|{red /24 o /64}"` y tope global por correo, comprobados antes de argon2 y sumados
  solo al fallar; el último admin activo queda exento de ambos y del bloqueo (S2-D10); una sola
  verificación de argon2 por rama (`dummy_verify` para inexistente, técnico, borrado y
  pendiente); un fallo suma `failed_login_count` con `UPDATE ... RETURNING` (L-10), bloquea a
  los `lock_after` consecutivos, emite `LoginAttempted` y confirma antes del 401 (S2-D8); todo
  401 se alarga hasta el piso `min_duration_ms` (S2-D39). Un éxito purga los refresh vencidos
  hace más de 30 días (L-4).
- `refresh`: `SELECT ... FOR UPDATE`, reuso real solo fuera de la gracia (M-2: revoca todo,
  fija `tokens_valid_after`, emite `SessionsRevoked` y confirma antes del 401), tope absoluto
  de la familia (L-4) y rotación que hereda `family_started_at`.
- `logout` por la cookie (H-1): revoca solo ese refresh, sin `replaced_by_id`.
- `configure_sleeper`: la espera del piso de duración es inyectable; las pruebas la sustituyen
  por un espía que no duerme.
Los logs nunca llevan el correo tecleado ni la clave del límite. `hash_password` y
`verify_password` cuestan CPU: se envuelven en `anyio.to_thread.run_sync`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.events import DomainEvent
from app.core.security import (
    Principal,
    TokenInvalid,
    WeakPasswordError,
    create_access_token,
    dummy_verify,
    hash_opaque_token,
    hash_password,
    needs_rehash,
    new_refresh_token,
    register_principal_loader,
    verify_password,
)
from app.core.security import validate_password_policy as _core_password_policy
from app.modules.auth import tokens
from app.modules.auth.exceptions import AuthError, InvalidCredentials, InvalidRefresh
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import (
    AUTH_FILTER,
    AuthPolicy,
    account_may_authenticate,
    is_active_admin,
    is_refresh_usable,
    is_reuse,
    should_auto_lock,
    user_status,
)
from app.modules.auth.schemas import Role, UserSummary

logger = logging.getLogger("app.auth")

SeedOutcome = Literal["created", "skipped"]


@dataclass(frozen=True, kw_only=True)
class UserCreated(DomainEvent):
    user_id: UUID
    role: str
    by: UUID


@dataclass(frozen=True)
class SeedResult:
    outcome: SeedOutcome
    user_id: UUID | None


LoginFailureReason = Literal["bad_password", "locked", "inactive", "pending"]
RevokeReason = Literal[
    "admin", "lock", "delete", "refresh_reuse", "password_changed", "password_reset"
]
USER_AGENT_EVENT_MAX: Final = 120  # L-8: el evento guarda el agente truncado
USER_AGENT_ROW_MAX: Final = 255  # columna `refresh_tokens.user_agent`
PURGE_EXPIRED_AFTER: Final = timedelta(days=30)  # L-4: purga oportunista en cada login
ACCOUNT_BUCKET: Final = "login-account"
ACCOUNT_GLOBAL_BUCKET: Final = "login-account-global"
_REASON_BY_STATUS: Final[dict[str, LoginFailureReason]] = {
    "locked": "locked",
    "inactive": "inactive",
    "pending_activation": "pending",
}


@dataclass(frozen=True, kw_only=True)
class LoginAttempted(DomainEvent):
    """Intento de login sobre una cuenta existente (nunca lleva el correo tecleado; N-31)."""

    user_id: UUID
    result: Literal["ok", "failed"]
    reason: LoginFailureReason | None = None
    ip: str
    user_agent: str | None = None


@dataclass(frozen=True, kw_only=True)
class SessionsRevoked(DomainEvent):
    user_id: UUID
    by: UUID
    revoked: int
    reason: RevokeReason


@dataclass(frozen=True, kw_only=True)
class UserLocked(DomainEvent):
    user_id: UUID
    by: UUID
    reason: Literal["admin", "too_many_failures"]


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    expires_in: int
    refresh_token: str
    user: UserSummary
    must_change_password: bool


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    expires_in: int
    refresh_token: str


Sleeper = Callable[[float], Awaitable[None]]
_sleeper: Sleeper = anyio.sleep


def configure_sleeper(sleeper: Sleeper | None) -> None:
    """Fija la espera del piso de duración (S2-D39); `None` vuelve a `anyio.sleep`."""
    global _sleeper
    _sleeper = sleeper if sleeper is not None else anyio.sleep


# Puras ---------------------------------------------------------------------------------


def validate_user_role(role: Role, member_id: UUID | None) -> None:
    if role == "member" and member_id is None:
        raise AuthError("member_id_required", "Un socio necesita su ficha.", field="member_id")
    if role != "member" and member_id is not None:
        raise AuthError(
            "member_id_not_allowed", "Admin y coach no llevan ficha de socio.", field="member_id"
        )


def normalize_login_email(email: str) -> str:
    return email.strip().lower()


def validate_password_policy(password: str, *, current_hash: str | None = None) -> None:
    try:
        _core_password_policy(password)
    except WeakPasswordError as error:
        raise AuthError(
            "weak_password", "La contraseña es demasiado débil.", field="password"
        ) from error
    if current_hash is not None and verify_password(current_hash, password):
        raise AuthError(
            "weak_password", "La contraseña nueva debe ser distinta de la actual.", field="password"
        )


def truncate(value: str | None, limit: int) -> str | None:
    return value[:limit] if value is not None else None


# Lecturas ---------------------------------------------------------------------------------


async def _active_admin(session: AsyncSession) -> User | None:
    filas = await session.scalars(select(User).where(User.role == "admin", AUTH_FILTER))
    return filas.first()


async def _active_admin_count(session: AsyncSession) -> int:
    total = await session.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", AUTH_FILTER)
    )
    return int(total or 0)


async def load_active_principal(session: AsyncSession, user_id: UUID) -> Principal | None:
    if user_id == SYSTEM_USER_ID:
        return None
    usuario = await session.scalar(
        select(User)
        .where(User.id == user_id, AUTH_FILTER)
        .execution_options(populate_existing=True)
    )
    if usuario is None:
        return None
    return Principal(
        usuario.id,
        usuario.role,  # type: ignore[arg-type]
        usuario.member_id,
        must_change_password=usuario.must_change_password,
        tokens_valid_after=usuario.tokens_valid_after,
    )


async def names_for(session: AsyncSession, user_ids: Sequence[UUID]) -> dict[UUID, str]:
    """Correo por id (los usuarios no tienen nombre; US-110)."""
    if not user_ids:
        return {}
    filas = await session.execute(select(User.id, User.email).where(User.id.in_(list(user_ids))))
    return {fila.id: fila.email for fila in filas}


async def ids_by_email(session: AsyncSession, emails: Sequence[str]) -> dict[str, UUID]:
    normalizados = [normalize_login_email(e) for e in emails]
    if not normalizados:
        return {}
    filas = await session.execute(
        select(User.email, User.id).where(User.email.in_(normalizados), User.deleted_at.is_(None))
    )
    return {fila.email: fila.id for fila in filas}


async def active_user_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    """Id de una persona en estado `active` (nunca `SYSTEM_USER_ID`), para `--as` (L-4)."""
    return await session.scalar(
        select(User.id).where(User.email == normalize_login_email(email), AUTH_FILTER)
    )


# Seed ---------------------------------------------------------------------------------------


async def seed_admin(
    session: AsyncSession, email: str, password: str, *, by: UUID, force_change: bool = True
) -> SeedResult:
    existente = await _active_admin(session)
    if existente is not None:
        return SeedResult("skipped", existente.id)
    validate_password_policy(password)
    correo = normalize_login_email(email)
    hashed = await anyio.to_thread.run_sync(hash_password, password)
    usuario = User(
        email=correo,
        password_hash=hashed,
        role="admin",
        member_id=None,
        must_change_password=force_change,
        created_by=by,
    )
    session.add(usuario)
    await session.flush()
    await events.emit(UserCreated(user_id=usuario.id, role="admin", by=by), session)
    return SeedResult("created", usuario.id)


# Login ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _LoginKeys:
    """Claves del límite por cuenta (H-4): (correo, red) y el tope global por correo."""

    account: str
    email: str


async def _find_login_user(session: AsyncSession, email: str) -> User | None:
    """Usuario no borrado con ese correo, distinto del técnico, leído fresco de la base."""
    return await session.scalar(
        select(User)
        .where(User.email == email, User.deleted_at.is_(None), User.id != SYSTEM_USER_ID)
        .execution_options(populate_existing=True)
    )


async def _is_exempt(session: AsyncSession, user: User | None) -> bool:
    """S2-D10 y H-4.3: el último admin activo solo tiene el límite por IP y argon2."""
    if user is None or not is_active_admin(user):
        return False
    return await _active_admin_count(session) <= 1


async def _check_account_limits(keys: _LoginKeys, policy: AuthPolicy) -> None:
    await ratelimit.enforce(
        ACCOUNT_BUCKET,
        keys.account,
        limit=policy.account_limit,
        window_s=policy.account_window_s,
        count=False,
    )
    await ratelimit.enforce(
        ACCOUNT_GLOBAL_BUCKET,
        keys.email,
        limit=policy.account_global_limit,
        window_s=policy.account_global_window_s,
        kind="account-global",
        count=False,
    )


async def _record_account_failure(keys: _LoginKeys, policy: AuthPolicy) -> None:
    await ratelimit.record(ACCOUNT_BUCKET, keys.account, window_s=policy.account_window_s)
    await ratelimit.record(
        ACCOUNT_GLOBAL_BUCKET,
        keys.email,
        window_s=policy.account_global_window_s,
        kind="account-global",
    )


async def _verify(user: User | None, password: str) -> bool:
    """M-6: exactamente una verificación de argon2 por rama; sin hash, contra el ficticio."""
    if user is None or user.password_hash is None:
        await anyio.to_thread.run_sync(dummy_verify, password)
        return False
    return await anyio.to_thread.run_sync(verify_password, user.password_hash, password)


async def _lock_for_failures(session: AsyncSession, user: User, now: datetime) -> None:
    """S2-D10.4: bloqueo persistente por fallos consecutivos; lo hace el sistema."""
    with actor_scope(SYSTEM_USER_ID):
        user.locked_at = now
        await session.flush()
        revocadas = await tokens.revoke_all(session, user.id, now=now)
        await events.emit(
            UserLocked(user_id=user.id, by=SYSTEM_USER_ID, reason="too_many_failures"), session
        )
        await events.emit(
            SessionsRevoked(user_id=user.id, by=SYSTEM_USER_ID, revoked=revocadas, reason="lock"),
            session,
        )
    logger.warning("cuenta bloqueada por fallos de login", extra={"user_id": str(user.id)})


async def _register_failure(
    session: AsyncSession,
    user: User,
    password_ok: bool,
    *,
    exempt: bool,
    ip: str,
    user_agent: str | None,
    policy: AuthPolicy,
) -> None:
    """Fallo sobre una cuenta existente: contador, bloqueo, evento y commit (S2-D8)."""
    now = current_clock().now_utc()
    if not password_ok and user.password_hash is not None:
        motivo: LoginFailureReason = "bad_password"
        fallos = await tokens.increment_failures(session, user.id)
        if user.locked_at is None and should_auto_lock(
            fallos, policy.lock_after, is_last_admin=exempt
        ):
            await _lock_for_failures(session, user, now)
    else:
        motivo = _REASON_BY_STATUS.get(user_status(user), "pending")
    with actor_scope(user.id):
        await events.emit(
            LoginAttempted(
                user_id=user.id,
                result="failed",
                reason=motivo,
                ip=ip,
                user_agent=truncate(user_agent, USER_AGENT_EVENT_MAX),
            ),
            session,
        )
        await tokens.commit_failure(session)
    logger.info("login rechazado", extra={"user_id": str(user.id), "motivo": motivo})


async def _wait_floor(started: float, policy: AuthPolicy) -> None:
    """S2-D39: todo 401 de login dura al menos `min_duration_ms`."""
    espera = policy.min_duration_ms / 1000 - (time.monotonic() - started)
    if espera > 0:
        await _sleeper(espera)


async def _issue_session(
    session: AsyncSession,
    user: User,
    password: str,
    *,
    ip: str,
    user_agent: str | None,
    policy: AuthPolicy,
) -> LoginResult:
    """Éxito: rehash si hace falta, contador a 0, purga L-4, refresh nuevo y access."""
    now = current_clock().now_utc()
    with actor_scope(user.id):
        if user.password_hash is not None and needs_rehash(user.password_hash):
            try:
                user.password_hash = await anyio.to_thread.run_sync(hash_password, password)
            except WeakPasswordError:
                logger.info("rehash omitido: la contraseña ya no cumple la política")
        await tokens.record_success(session, user.id, now=now)
        await tokens.purge_expired_for_user(
            session, user.id, now=now, older_than=PURGE_EXPIRED_AFTER
        )
        claro, token_hash = new_refresh_token()
        session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=now + policy.refresh_ttl,
                user_agent=truncate(user_agent, USER_AGENT_ROW_MAX),
                family_started_at=now,
                created_by=user.id,
            )
        )
        await session.flush()
        await events.emit(
            LoginAttempted(
                user_id=user.id,
                result="ok",
                ip=ip,
                user_agent=truncate(user_agent, USER_AGENT_EVENT_MAX),
            ),
            session,
        )
    acceso = create_access_token(user.id, user.role, user.member_id, current_clock())  # type: ignore[arg-type]
    return LoginResult(
        access_token=acceso,
        expires_in=policy.access_ttl_s,
        refresh_token=claro,
        user=UserSummary(id=user.id, email=user.email, role=user.role),
        must_change_password=user.must_change_password,
    )


async def login(
    session: AsyncSession,
    email: str,
    password: str,
    *,
    ip: str,
    user_agent: str | None,
    policy: AuthPolicy,
) -> LoginResult:
    inicio = time.monotonic()
    correo = normalize_login_email(email)
    claves = _LoginKeys(account=f"{correo}|{ratelimit.ip_bucket_key(ip)}", email=correo)
    usuario = await _find_login_user(session, correo)
    exento = await _is_exempt(session, usuario)
    if not exento:
        await _check_account_limits(claves, policy)  # 429 antes de argon2, sin sumar
    correcta = await _verify(usuario, password)
    if usuario is not None and correcta and account_may_authenticate(usuario):
        return await _issue_session(
            session, usuario, password, ip=ip, user_agent=user_agent, policy=policy
        )
    if not exento:
        await _record_account_failure(claves, policy)
    if usuario is None:
        logger.info("login rechazado", extra={"motivo": "unknown_account"})
    else:
        await _register_failure(
            session,
            usuario,
            correcta,
            exempt=exento,
            ip=ip,
            user_agent=user_agent,
            policy=policy,
        )
    await _wait_floor(inicio, policy)
    raise InvalidCredentials()


# Refresh y logout -----------------------------------------------------------------------------


async def _locked_refresh_row(session: AsyncSession, token: str | None) -> RefreshToken | None:
    """La fila del refresh con `FOR UPDATE`: dos refresh simultáneos se serializan."""
    if not token:
        return None
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    return await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _revoke_family_for_reuse(
    session: AsyncSession, fila: RefreshToken, now: datetime
) -> None:
    """N-13 fuera de la gracia: se cierran todas las sesiones y el efecto sobrevive al 401."""
    with actor_scope(SYSTEM_USER_ID):
        revocadas = await tokens.revoke_all(session, fila.user_id, now=now)
        await events.emit(
            SessionsRevoked(
                user_id=fila.user_id,
                by=SYSTEM_USER_ID,
                revoked=revocadas,
                reason="refresh_reuse",
            ),
            session,
        )
        await tokens.commit_failure(session)
    logger.warning("reuso de refresh: sesiones revocadas", extra={"user_id": str(fila.user_id)})


async def refresh(
    session: AsyncSession, token: str | None, *, user_agent: str | None, policy: AuthPolicy
) -> RefreshResult:
    fila = await _locked_refresh_row(session, token)
    if fila is None:
        raise InvalidRefresh()
    now = current_clock().now_utc()
    if is_reuse(fila, now, policy.reuse_grace):
        await _revoke_family_for_reuse(session, fila, now)
        raise InvalidRefresh()
    usuario = await session.scalar(
        select(User).where(User.id == fila.user_id).execution_options(populate_existing=True)
    )
    if usuario is None or not is_refresh_usable(
        fila, usuario, now, absolute_ttl=policy.refresh_absolute_ttl
    ):
        error = InvalidRefresh()
        if fila.revoked_at is not None and fila.replaced_by_id is not None:
            # M-2: concurrencia benigna; la otra petición ya puso la cookie nueva y borrarla
            # aquí cerraría la sesión que acaba de rotar.
            error.clear_cookie = False
            logger.info("refresh rotado dentro de la gracia", extra={"user_id": str(fila.user_id)})
        raise error
    with actor_scope(usuario.id):
        claro, token_hash = new_refresh_token()
        sucesor = RefreshToken(
            user_id=usuario.id,
            token_hash=token_hash,
            expires_at=now + policy.refresh_ttl,
            user_agent=truncate(user_agent, USER_AGENT_ROW_MAX),
            family_started_at=fila.family_started_at,
            created_by=usuario.id,
        )
        session.add(sucesor)
        await session.flush()
        fila.revoked_at = now
        fila.replaced_by_id = sucesor.id
        await session.flush()
    acceso = create_access_token(usuario.id, usuario.role, usuario.member_id, current_clock())  # type: ignore[arg-type]
    return RefreshResult(access_token=acceso, expires_in=policy.access_ttl_s, refresh_token=claro)


async def logout(session: AsyncSession, token: str | None) -> None:
    """H-1: revoca solo el refresh de la cookie; sin token, desconocido o ya revocado, nada."""
    fila = await _locked_refresh_row(session, token)
    if fila is None or fila.revoked_at is not None:
        return
    with actor_scope(fila.user_id):
        fila.revoked_at = current_clock().now_utc()
        await session.flush()


register_principal_loader(load_active_principal)

__all__ = [
    "LoginAttempted",
    "LoginResult",
    "RefreshResult",
    "SessionsRevoked",
    "UserCreated",
    "UserLocked",
    "active_user_id_by_email",
    "configure_sleeper",
    "ids_by_email",
    "is_active_admin",
    "load_active_principal",
    "login",
    "logout",
    "names_for",
    "normalize_login_email",
    "refresh",
    "seed_admin",
    "user_status",
    "validate_password_policy",
    "validate_user_role",
]
