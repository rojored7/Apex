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
- S2-B3 (US-045, US-046, US-047): `me` (usuario vigente más
  `settings.service.gym_name`, S2-D14), `change_password` (verifica la actual, política con
  `field="new_password"`, `revoke_all(except_id=<refresh de la cookie>)` que fija
  `tokens_valid_after` y devuelve un access nuevo; H-3, S2-D37), `list_users` (sin el técnico,
  `q` escapado, orden por correo, `active_sessions`) y `create_user` (admin o coach sin hash,
  token `activate` de 72 h, `EmailTaken`; L-2). Evento `PasswordChanged` con
  `via_link_issued_by` (L-13).
- S2-B4 (US-048, US-052): `reset`, `forgot` (H-2: no escribe nada; tope por cuenta
  `FORGOT_ACCOUNT_*`), `resend_link` (L-13) e `issue_link` (el mismo enlace sin L-13, solo
  para `cli issue-reset-link`).
- S2-B5 (US-049, US-050, US-051): `get_user` (incluye borrados; el técnico da 404),
  `update_user` (correo único entre no borrados y rol con `validate_user_role` y `LastAdmin`),
  `delete_user` (baja lógica, `revoke_all` y `SessionsRevoked(reason="delete")`), `lock`
  (`UserLocked(reason="admin")` y `SessionsRevoked(reason="lock")` en una transacción),
  `unlock` (limpia `locked_at`, `failed_login_count` y los contadores en memoria con
  `ratelimit.forget`; S2-D10) y `revoke_sessions` (`SessionsRevoked(reason="admin")` también
  con 0; H-3).
Los logs nunca llevan el correo tecleado ni la clave del límite. `hash_password` y
`verify_password` cuestan CPU: se envuelven en `anyio.to_thread.run_sync`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Final, Literal
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.errors import UnauthorizedError
from app.core.events import DomainEvent
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.security import (
    SESSION_INVALID_MESSAGE,
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
from app.modules.auth import rules, tokens
from app.modules.auth.exceptions import (
    AuthError,
    EmailTaken,
    InvalidCredentials,
    InvalidCurrentPassword,
    InvalidRefresh,
    InvalidToken,
    LastAdmin,
    NotLocked,
    UserNotEligible,
)
from app.modules.auth.models import OneTimeToken, RefreshToken, User
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
from app.modules.auth.schemas import (
    AccessTokenOut,
    CreateUserOut,
    IssuedLinkOut,
    MeOut,
    Role,
    StaffRole,
    UserRow,
    UserStatus,
    UserSummary,
)

# Arista `auth → settings` del grafo de services (S2-D53): import a nivel de módulo.
from app.modules.settings import service as settings_service

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
EMAIL_ALIVE_INDEX: Final = "uq_users_email_alive"
PURGE_EXPIRED_AFTER: Final = timedelta(days=30)  # L-4: purga oportunista en cada login
ACCOUNT_BUCKET: Final = "login-account"
ACCOUNT_GLOBAL_BUCKET: Final = "login-account-global"
# Fallos de la contraseña actual en `POST /auth/me/password`, por usuario (revisión S2-B3).
CHANGE_PASSWORD_BUCKET: Final = "change-password-user"  # noqa: S105 - nombre de bucket
CHANGE_PASSWORD_USER_LIMIT: Final = 5
CHANGE_PASSWORD_USER_WINDOW_S: Final = 900
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


PasswordChangeVia = Literal["change", "activate", "reset"]


@dataclass(frozen=True, kw_only=True)
class PasswordChanged(DomainEvent):
    """Contraseña nueva (US-046, US-048). `via_link_issued_by` es el `created_by` del enlace
    con que se fijó (L-13); `None` en un cambio desde "Mi cuenta"."""

    user_id: UUID
    by: UUID
    via: PasswordChangeVia
    via_link_issued_by: UUID | None = None


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
    """La de `rules` con `field="password"` (seed y CLI); cambio y reset usan `new_password`."""
    rules.validate_password_policy(password, current_hash=current_hash)


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
        if is_active_admin(user):
            # Revisión S2-B5 (MEDIUM-1): el candado de admins, ANTES del `UPDATE` del contador
            # (orden admins → usuario de `lock` y `delete_user`), serializa dos bloqueos
            # automáticos simultáneos; el segundo ve el conjunto reducido y queda exento.
            admins = await tokens.lock_active_admins(session)
            exempt = rules.would_remove_last_admin(admins, user.id, new_role=None, deleting=True)
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
    """La fila del refresh con `FOR UPDATE`, sin el usuario (solo `logout`, que revoca esa
    fila y nada más; `refresh` usa `_locked_refresh_and_owner`)."""
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


async def _locked_refresh_and_owner(
    session: AsyncSession, token: str | None
) -> tuple[RefreshToken, User] | None:
    """El refresh y su dueño con `FOR UPDATE`, en el orden usuario → token del módulo (S2-B5;
    cierra B3 MEDIUM-2): el `user_id` se lee sin candado, luego se bloquea el usuario y después
    la fila del token, leída fresca. Así una revocación (`revoke_sessions`, `lock`, `delete`,
    `change_password`), que toma el usuario antes que sus refresh, y una rotación se
    serializan en el usuario, y ningún sucesor creado durante la revocación sobrevive."""
    if not token:
        return None
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    dueno = await session.scalar(
        select(RefreshToken.user_id).where(RefreshToken.token_hash == token_hash)
    )
    if dueno is None:
        return None
    usuario = await session.scalar(
        select(User)
        .where(User.id == dueno)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None or fila is None:
        return None
    return fila, usuario


async def refresh(
    session: AsyncSession, token: str | None, *, user_agent: str | None, policy: AuthPolicy
) -> RefreshResult:
    encontrado = await _locked_refresh_and_owner(session, token)
    if encontrado is None:
        raise InvalidRefresh()
    fila, usuario = encontrado
    now = current_clock().now_utc()
    if is_reuse(fila, now, policy.reuse_grace):
        await _revoke_family_for_reuse(session, fila, now)
        raise InvalidRefresh()
    if not is_refresh_usable(fila, usuario, now, absolute_ttl=policy.refresh_absolute_ttl):
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


# Mi cuenta y usuarios (S2-B3) -------------------------------------------------------------


async def _fresh_user(
    session: AsyncSession, user_id: UUID, *, for_update: bool = False
) -> User | None:
    """El usuario leído de la base; `for_update` serializa dos cambios de contraseña."""
    consulta = select(User).where(User.id == user_id)
    if for_update:
        consulta = consulta.with_for_update()
    return await session.scalar(consulta.execution_options(populate_existing=True))


async def me(session: AsyncSession, principal: Principal) -> MeOut:
    """S2-D14: el usuario vigente (el cargador ya lo validó) y el nombre del gimnasio."""
    usuario = await _fresh_user(session, principal.user_id)
    if usuario is None:  # el cargador lo acaba de leer; solo una carrera llega aquí
        raise UnauthorizedError("unauthorized", SESSION_INVALID_MESSAGE)
    return MeOut(
        id=usuario.id,
        email=usuario.email,
        role=usuario.role,
        member_id=usuario.member_id,
        gym_name=await settings_service.gym_name(session),
        must_change_password=usuario.must_change_password,
    )


async def _own_refresh_id(session: AsyncSession, user_id: UUID, token: str | None) -> UUID | None:
    """Id del refresh de la cookie si es del mismo usuario; otro o ilegible no protege nada."""
    if not token:
        return None
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    return await session.scalar(
        select(RefreshToken.id).where(
            RefreshToken.token_hash == token_hash, RefreshToken.user_id == user_id
        )
    )


async def change_password(
    session: AsyncSession,
    user_id: UUID,
    current_password: str,
    new_password: str,
    *,
    current_refresh: str | None,
    policy: AuthPolicy,
) -> AccessTokenOut:
    """US-046 (H-3, S2-D37, M-8): actual, política, hash nuevo, corte y access nuevo.

    Orden fijo: la actual primero (`InvalidCurrentPassword`), luego la política con
    `field="new_password"` (incluida "distinta de la actual"). Un solo `update` auditado de
    `auth.users`; `revoke_all` deja viva la sesión de la cookie y fija `tokens_valid_after`
    aunque no haya otras sesiones.
    """
    clave = str(user_id)
    await ratelimit.enforce(  # antes de argon2 y sin sumar (como el límite por cuenta)
        CHANGE_PASSWORD_BUCKET,
        clave,
        limit=CHANGE_PASSWORD_USER_LIMIT,
        window_s=CHANGE_PASSWORD_USER_WINDOW_S,
        kind="user",
        count=False,
    )
    usuario = await _fresh_user(session, user_id, for_update=True)
    if not await _verify(usuario, current_password) or usuario is None:
        await ratelimit.record(
            CHANGE_PASSWORD_BUCKET, clave, window_s=CHANGE_PASSWORD_USER_WINDOW_S, kind="user"
        )
        logger.info("cambio de contraseña rechazado", extra={"user_id": clave})
        raise InvalidCurrentPassword(field="current_password")
    await anyio.to_thread.run_sync(
        partial(
            rules.validate_password_policy,
            new_password,
            current_hash=usuario.password_hash,
            field="new_password",
        )
    )
    nuevo_hash = await anyio.to_thread.run_sync(hash_password, new_password)
    now = current_clock().now_utc()
    usuario.password_hash = nuevo_hash
    usuario.must_change_password = False
    usuario.failed_login_count = 0
    await session.flush()
    # Revisión S2-B4 (MEDIUM-1): un enlace abierto no sobrevive al cambio de contraseña.
    await tokens.close_open_one_time_tokens(session, user_id, now=now)
    conservar = await _own_refresh_id(session, user_id, current_refresh)
    revocadas = await tokens.revoke_all(session, user_id, now=now, except_id=conservar)
    await events.emit(
        PasswordChanged(user_id=user_id, by=user_id, via="change", via_link_issued_by=None),
        session,
    )
    if revocadas:
        await events.emit(
            SessionsRevoked(
                user_id=user_id, by=user_id, revoked=revocadas, reason="password_changed"
            ),
            session,
        )
    logger.info(
        "contraseña cambiada", extra={"user_id": str(user_id), "sesiones_revocadas": revocadas}
    )
    acceso = create_access_token(usuario.id, usuario.role, usuario.member_id, current_clock())  # type: ignore[arg-type]
    return AccessTokenOut(access_token=acceso, expires_in=policy.access_ttl_s)


async def _active_sessions(session: AsyncSession, user_ids: Sequence[UUID]) -> dict[UUID, int]:
    """Refresh vigentes (`expires_at > ahora`, reloj de la app) y no revocados, por usuario."""
    if not user_ids:
        return {}
    now = current_clock().now_utc()
    filas = await session.execute(
        select(RefreshToken.user_id, func.count())
        .where(
            RefreshToken.user_id.in_(list(user_ids)),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .group_by(RefreshToken.user_id)
    )
    return {user_id: int(total) for user_id, total in filas.all()}


async def list_users(
    session: AsyncSession,
    *,
    q: str | None,
    role: Role | None,
    status: UserStatus | None,
    page: PageParams,
) -> Page[UserRow]:
    """US-045: sin el técnico; sin `status` excluye borrados; `q` sobre el correo con `ILIKE`
    escapado; orden por correo; `active_sessions` en una sola consulta agregada por página."""
    consulta = select(User).where(User.id != SYSTEM_USER_ID)
    consulta = consulta.where(
        User.deleted_at.is_(None) if status is None else rules.status_filter(status)
    )
    if role is not None:
        consulta = consulta.where(User.role == role)
    if q:
        patron = "%" + rules.escape_like(q) + "%"  # valor ligado, nunca texto SQL
        consulta = consulta.where(User.email.ilike(patron, escape=rules.LIKE_ESCAPE))
    usuarios, total = await paginate(session, consulta.order_by(User.email.asc()), page)
    sesiones = await _active_sessions(session, [u.id for u in usuarios])
    filas = [rules.user_row(u, active_sessions=sesiones.get(u.id, 0)) for u in usuarios]
    return to_page(filas, total, page)


async def _alive_user_id(session: AsyncSession, email: str) -> UUID | None:
    return await session.scalar(
        select(User.id).where(User.email == email, User.deleted_at.is_(None))
    )


def _is_email_conflict(error: IntegrityError) -> bool:
    return EMAIL_ALIVE_INDEX in str(error.orig)


async def create_user(
    session: AsyncSession, *, email: str, role: StaffRole, by: UUID, front_base_url: str
) -> CreateUserOut:
    """US-047 (L-2): admin o coach sin hash (`pending_activation`), token `activate` de 72 h y
    `activation_url`, que viaja una sola vez y nunca se registra. El correo de una cuenta viva
    da `EmailTaken`; la carrera la decide `uq_users_email_alive` dentro de un savepoint."""
    correo = normalize_login_email(email)
    existente = await _alive_user_id(session, correo)
    if existente is not None:
        raise EmailTaken(field="email", existing_id=existente)
    usuario = User(
        email=correo,
        password_hash=None,
        role=role,
        member_id=None,
        is_active=True,
        must_change_password=False,
        created_by=by,
    )
    try:
        async with session.begin_nested():
            session.add(usuario)
            await session.flush()
    except IntegrityError as error:
        if not _is_email_conflict(error):
            raise
        ganador = await _alive_user_id(session, correo)
        raise EmailTaken(field="email", existing_id=ganador) from None
    now = current_clock().now_utc()
    claro, fila = await tokens.issue_one_time_token(session, usuario.id, "activate", now=now)
    await events.emit(UserCreated(user_id=usuario.id, role=role, by=by), session)
    logger.info("cuenta creada", extra={"user_id": str(usuario.id), "role": role})
    return CreateUserOut(
        user=rules.user_out(usuario),
        activation_url=rules.activation_url(front_base_url, claro),
        expires_at=fila.expires_at,
    )


# Activación, recuperación y reenvío (S2-B4) -------------------------------------------------

# S2-D36 (H-2): tope por cuenta de `forgot`, además de `rate_limit("forgot")` por IP. Cuenta todo
# intento sobre el correo normalizado, exista o no la cuenta.
FORGOT_ACCOUNT_BUCKET: Final = "forgot-account"
FORGOT_ACCOUNT_LIMIT: Final = 5
FORGOT_ACCOUNT_WINDOW_S: Final = 3600


# Estados que pueden recibir un enlace: los demás (bloqueado, borrado, inactivo) no lo podrían
# usar (`rules.is_one_time_token_usable`).
_LINK_ELIGIBLE: Final[frozenset[UserStatus]] = frozenset({"active", "pending_activation"})


async def _locked_one_time_token(
    session: AsyncSession, token: str
) -> tuple[OneTimeToken, User] | None:
    """El token y su usuario con `FOR UPDATE`, siempre en el orden usuario → token (el mismo de
    `resend_link`, `issue_link` y `change_password`; sin él, una emisión concurrente podría dar
    un interbloqueo). Dos `reset` con el mismo token se serializan en el usuario y el segundo
    lee `used_at` fresco."""
    try:
        token_hash = hash_opaque_token(token)
    except TokenInvalid:
        return None
    dueno = await session.scalar(
        select(OneTimeToken.user_id).where(OneTimeToken.token_hash == token_hash)
    )
    if dueno is None:
        return None
    usuario = await session.scalar(
        select(User)
        .where(User.id == dueno)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fila = await session.scalar(
        select(OneTimeToken)
        .where(OneTimeToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None or fila is None:
        return None
    return fila, usuario


async def reset(session: AsyncSession, token: str, new_password: str) -> None:
    """US-048 (blueprint S2-B4, decisión 7; H-3, S2-D37, S2-D40, L-13): token con `FOR
    UPDATE` (`InvalidToken`), política con `field="new_password"`, hash nuevo y token usado
    bajo `actor_scope(token.user_id)`; con `reset`, `revoke_all` y `SessionsRevoked`;
    `PasswordChanged(via=<propósito>, via_link_issued_by=<created_by del token>)`. No inicia
    sesión."""
    encontrado = await _locked_one_time_token(session, token)
    now = current_clock().now_utc()
    if encontrado is None or not rules.is_one_time_token_usable(*encontrado, now):
        logger.info("enlace de un solo uso rechazado")
        raise InvalidToken()
    fila, usuario = encontrado
    rules.validate_password_policy(new_password, field="new_password")
    nuevo_hash = await anyio.to_thread.run_sync(hash_password, new_password)
    via: Literal["activate", "reset"] = "activate" if fila.purpose == "activate" else "reset"
    with actor_scope(usuario.id):
        fila.used_at = now
        usuario.password_hash = nuevo_hash
        usuario.must_change_password = False
        usuario.failed_login_count = 0
        await session.flush()
        # Revisión S2-B4 (MEDIUM-1): ningún otro enlace abierto sobrevive a la contraseña nueva.
        await tokens.close_open_one_time_tokens(session, usuario.id, now=now)
        if via == "reset":
            revocadas = await tokens.revoke_all(session, usuario.id, now=now)
            if revocadas:
                await events.emit(
                    SessionsRevoked(
                        user_id=usuario.id,
                        by=usuario.id,
                        revoked=revocadas,
                        reason="password_reset",
                    ),
                    session,
                )
        await events.emit(
            PasswordChanged(
                user_id=usuario.id, by=usuario.id, via=via, via_link_issued_by=fila.created_by
            ),
            session,
        )
        await session.flush()
    logger.info("contraseña fijada por enlace", extra={"user_id": str(usuario.id), "via": via})


async def forgot(session: AsyncSession, email: str, *, ip: str, policy: AuthPolicy) -> None:
    """US-048 en v0.1 (S2-D36, H-2): no escribe nada. Normaliza, cuenta el intento en
    `FORGOT_ACCOUNT_BUCKET`, espera el piso `policy.min_duration_ms` con el sleeper de
    `configure_sleeper` (S2-D39) exista o no la cuenta y deja un log sin el correo.

    Ni siquiera consulta la base: sin emisor (US-131) no hay nada que hacer con la cuenta, y no
    leerla quita de raíz cualquier diferencia de tiempo entre un correo existente y uno que no.
    `session` e `ip` quedan en la firma para el emisor real."""
    del session, ip  # v0.1: sin lectura ni escritura (H-2)
    inicio = time.monotonic()
    await ratelimit.enforce(
        FORGOT_ACCOUNT_BUCKET,
        normalize_login_email(email),
        limit=FORGOT_ACCOUNT_LIMIT,
        window_s=FORGOT_ACCOUNT_WINDOW_S,
    )
    logger.info("forgot recibido; v0.1 no envía enlaces (US-131)")
    await _wait_floor(inicio, policy)


def _ensure_link_eligible(usuario: User) -> None:
    if rules.user_status(usuario) not in _LINK_ELIGIBLE:
        raise UserNotEligible()


async def _issue_link_for(
    session: AsyncSession, usuario: User, *, by: UUID, front_base_url: str
) -> IssuedLinkOut:
    """Emite el enlace de `link_purpose_for` atribuido a `by` (`created_by` y auditoría)."""
    proposito = rules.link_purpose_for(usuario)
    with actor_scope(by):
        claro, fila = await tokens.issue_one_time_token(
            session, usuario.id, proposito, now=current_clock().now_utc()
        )
    logger.info(
        "enlace emitido",
        extra={"user_id": str(usuario.id), "purpose": proposito, "by": str(by)},
    )
    return IssuedLinkOut(
        url=rules.activation_url(front_base_url, claro),
        purpose=proposito,
        expires_at=fila.expires_at,
    )


async def issue_link(
    session: AsyncSession, user_id: UUID, *, by: UUID, front_base_url: str
) -> IssuedLinkOut:
    """El enlace de `link_purpose_for(user)` sin la regla L-13 (solo `cli issue-reset-link`):
    `get_alive_or_404(include_deleted=True)`; bloqueado o borrado dan `UserNotEligible`."""
    usuario = await tokens.get_alive_or_404(session, user_id, include_deleted=True, for_update=True)
    _ensure_link_eligible(usuario)
    return await _issue_link_for(session, usuario, by=by, front_base_url=front_base_url)


async def resend_link(
    session: AsyncSession, user_id: UUID, *, by: UUID, front_base_url: str
) -> IssuedLinkOut:
    """US-052 (blueprint S2-B4; L-13): `UserNotFound` para el técnico o un id inexistente;
    `UserNotEligible` si está bloqueado o borrado, si es la cuenta de `by` o si es otro admin
    activo con contraseña; si no, `issue_one_time_token` del propósito de `link_purpose_for`
    y `IssuedLinkOut` con `url = <front_base_url sin barra final>/restablecer/<token>`."""
    usuario = await tokens.get_alive_or_404(session, user_id, include_deleted=True, for_update=True)
    _ensure_link_eligible(usuario)
    if usuario.id == by or is_active_admin(usuario):
        # L-13: un admin no recupera su cuenta ni la de otro admin activo por aquí.
        logger.info("reenvío rechazado por L-13", extra={"user_id": str(usuario.id)})
        raise UserNotEligible()
    return await _issue_link_for(session, usuario, by=by, front_base_url=front_base_url)


async def active_admin_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    """Id de un admin en estado `active` (para el `--as` de `cli issue-reset-link`)."""
    return await session.scalar(
        select(User.id).where(
            User.email == normalize_login_email(email), User.role == "admin", AUTH_FILTER
        )
    )


# Ciclo de vida del usuario (S2-B5) --------------------------------------------------------


async def get_user(session: AsyncSession, user_id: UUID) -> User:
    """US-049: la cuenta, incluidas las borradas (con su estado); técnico o inexistente dan
    `UserNotFound`."""
    return await tokens.get_alive_or_404(session, user_id, include_deleted=True)


async def _check_email_free(session: AsyncSession, usuario: User, correo: str) -> None:
    """Pre-chequeo de `update_user`: otra cuenta viva con ese correo da `EmailTaken`."""
    existente = await _alive_user_id(session, correo)
    if existente is not None and existente != usuario.id:
        raise EmailTaken(field="email", existing_id=existente)


def _check_role_change(usuario: User, new_role: Role, active_admins: frozenset[UUID]) -> None:
    validate_user_role(new_role, usuario.member_id)
    if rules.would_remove_last_admin(active_admins, usuario.id, new_role=new_role, deleting=False):
        raise LastAdmin()


async def update_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    email: str | None,
    role: Role | None,
    by: UUID,
) -> User:
    """US-049: `UserNotFound` si está borrada (o es el técnico); correo normalizado y único entre
    no borrados (`EmailTaken` con `existing_id`; la carrera la decide `uq_users_email_alive` en
    un `begin_nested()`); si cambia el rol, `validate_user_role` con el `member_id` actual y
    `LastAdmin` si dejaría el sistema sin admin activo. `None` no cambia el campo.

    Candados: con `role`, primero los admins activos (`lock_active_admins`, `ORDER BY id`) y
    luego la cuenta; así dos degradaciones o una degradación y una baja se serializan."""
    admins = await tokens.lock_active_admins(session) if role is not None else frozenset()
    usuario = await tokens.get_alive_or_404(session, user_id, for_update=True)
    nuevo_rol = role if role is not None and role != usuario.role else None
    correo = normalize_login_email(email) if email is not None else None
    nuevo_correo = correo if correo is not None and correo != usuario.email else None
    if nuevo_rol is not None:
        _check_role_change(usuario, nuevo_rol, admins)
    if nuevo_correo is not None:
        await _check_email_free(session, usuario, nuevo_correo)
    if nuevo_rol is None and nuevo_correo is None:
        return usuario
    try:
        async with session.begin_nested():
            if nuevo_rol is not None:
                usuario.role = nuevo_rol
            if nuevo_correo is not None:
                usuario.email = nuevo_correo
            await session.flush()
    except IntegrityError as error:
        if not _is_email_conflict(error) or nuevo_correo is None:
            raise
        ganador = await _alive_user_id(session, nuevo_correo)
        raise EmailTaken(field="email", existing_id=ganador) from None
    if nuevo_correo is not None:
        # Revisión S2-B5 (LOW-3): un enlace entregado al correo anterior deja de servir.
        await tokens.close_open_one_time_tokens(session, usuario.id, now=current_clock().now_utc())
    logger.info(
        "cuenta editada",
        extra={
            "user_id": str(usuario.id),
            "by": str(by),
            "cambio_rol": nuevo_rol is not None,
            "cambio_correo": nuevo_correo is not None,
        },
    )
    return usuario


async def delete_user(session: AsyncSession, user_id: UUID, *, by: UUID) -> None:
    """US-049: baja lógica (`deleted_at = now`, nunca `session.delete`); `LastAdmin` si es el
    último admin activo; `revoke_all` en la misma transacción y
    `SessionsRevoked(reason="delete", revoked=n)`. Candados: admins activos y luego la cuenta
    (dos bajas simultáneas de los dos últimos admins dejan exactamente uno)."""
    admins = await tokens.lock_active_admins(session)
    usuario = await tokens.get_alive_or_404(session, user_id, for_update=True)
    if rules.would_remove_last_admin(admins, usuario.id, new_role=None, deleting=True):
        raise LastAdmin()
    now = current_clock().now_utc()
    usuario.deleted_at = now  # por ORM: queda el `update` auditado por el actor
    await session.flush()
    revocadas = await tokens.revoke_all(session, usuario.id, now=now)
    await events.emit(
        SessionsRevoked(user_id=usuario.id, by=by, revoked=revocadas, reason="delete"), session
    )
    logger.info(
        "cuenta dada de baja",
        extra={"user_id": str(usuario.id), "by": str(by), "sesiones_revocadas": revocadas},
    )


async def lock(session: AsyncSession, user_id: UUID, *, by: UUID) -> User:
    """US-050: `get_alive_or_404`, `lock_active_admins`, `lock_precondition`, `locked_at = now`,
    `revoke_all`, `UserLocked(reason="admin")` y `SessionsRevoked(reason="lock")`. Todo en una
    transacción: si un handler falla no queda nada aplicado. Candados: admins activos y luego
    la cuenta (el orden de `delete_user` y `update_user`)."""
    admins = await tokens.lock_active_admins(session)
    usuario = await tokens.get_alive_or_404(session, user_id, for_update=True)
    rules.lock_precondition(
        usuario,
        by,
        is_last_admin=rules.would_remove_last_admin(
            admins, usuario.id, new_role=None, deleting=True
        ),
    )
    now = current_clock().now_utc()
    usuario.locked_at = now  # por ORM: queda el `update` auditado por el actor
    await session.flush()
    revocadas = await tokens.revoke_all(session, usuario.id, now=now)
    await events.emit(UserLocked(user_id=usuario.id, by=by, reason="admin"), session)
    await events.emit(
        SessionsRevoked(user_id=usuario.id, by=by, revoked=revocadas, reason="lock"), session
    )
    logger.info(
        "cuenta bloqueada por un admin",
        extra={"user_id": str(usuario.id), "by": str(by), "sesiones_revocadas": revocadas},
    )
    return usuario


async def unlock(session: AsyncSession, user_id: UUID, *, by: UUID) -> User:
    """US-050 (S2-D10, H-4.5): `NotLocked` si no está bloqueada; `locked_at = None`,
    `failed_login_count = 0`, `ratelimit.forget` de los contadores por cuenta y cierre de los
    enlaces abiertos (revisión S2-B4). Las sesiones siguen revocadas; sin eventos de dominio.

    Los contadores en memoria se olvidan al final, tras escribir en la base: son del proceso
    del api (el CLI corre en otro y no los alcanza; RUNBOOK)."""
    usuario = await tokens.get_alive_or_404(session, user_id, for_update=True)
    if usuario.locked_at is None:
        raise NotLocked()
    now = current_clock().now_utc()
    usuario.locked_at = None  # por ORM: queda el `update` auditado por el actor
    usuario.failed_login_count = 0  # fuera de la auditoría (L-10)
    await session.flush()
    await tokens.close_open_one_time_tokens(session, usuario.id, now=now)
    await ratelimit.forget(ACCOUNT_BUCKET, usuario.email)
    await ratelimit.forget(ACCOUNT_GLOBAL_BUCKET, usuario.email, kind="account-global")
    logger.info("cuenta desbloqueada", extra={"user_id": str(usuario.id), "by": str(by)})
    return usuario


async def revoke_sessions(session: AsyncSession, user_id: UUID, *, by: UUID) -> int:
    """US-051 (H-3): revoca todos los refresh, fija `tokens_valid_after` y emite
    `SessionsRevoked(reason="admin", revoked=n)` también con `n = 0`. No bloquea la cuenta.
    Bloquea primero el usuario y luego sus refresh (orden usuario → token, como `refresh`)."""
    usuario = await tokens.get_alive_or_404(session, user_id, for_update=True)
    now = current_clock().now_utc()
    revocadas = await tokens.revoke_all(session, usuario.id, now=now)
    await events.emit(
        SessionsRevoked(user_id=usuario.id, by=by, revoked=revocadas, reason="admin"), session
    )
    logger.info(
        "sesiones cerradas por un admin",
        extra={"user_id": str(usuario.id), "by": str(by), "sesiones_revocadas": revocadas},
    )
    return revocadas


register_principal_loader(load_active_principal)

__all__ = [
    "LoginAttempted",
    "LoginResult",
    "PasswordChanged",
    "RefreshResult",
    "SessionsRevoked",
    "UserCreated",
    "UserLocked",
    "active_admin_id_by_email",
    "active_user_id_by_email",
    "change_password",
    "configure_sleeper",
    "create_user",
    "delete_user",
    "forgot",
    "get_user",
    "ids_by_email",
    "is_active_admin",
    "issue_link",
    "list_users",
    "load_active_principal",
    "lock",
    "login",
    "logout",
    "me",
    "names_for",
    "normalize_login_email",
    "refresh",
    "resend_link",
    "reset",
    "revoke_sessions",
    "seed_admin",
    "unlock",
    "update_user",
    "user_status",
    "validate_password_policy",
    "validate_user_role",
]
