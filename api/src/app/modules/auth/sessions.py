"""Sesiones de auth: login, refresh, logout y el cargador del principal (S2-B2: US-042, US-043,
US-044; adaptador del puerto `PrincipalLoader` de US-034). Privado del módulo (revisión Python
H1); se usa a través de `auth.service`.

- `load_active_principal`: el cargador real de `current_user`, con `rules.AUTH_FILTER` (M-7);
  trae `must_change_password` y `tokens_valid_after` (H-3). Lo registra `service.py`.
- `login` (blueprint 7.1 corregido por H-4 y M-6; revisión del Sprint 2, N-3 y M2): límite
  por cuenta con clave `"{correo}|{IPv4 exacta o /64}"` y tope global por correo, reservados
  de forma atómica antes de argon2 y devueltos si el login sale bien (solo cuentan los
  fallos); el último admin activo queda exento de ambos y del bloqueo (S2-D10); una sola
  verificación de argon2 por rama (`verify_password_or_dummy`: `dummy_verify` para
  inexistente, técnico, borrado y pendiente); un fallo suma `failed_login_count` con
  `UPDATE ... RETURNING` (L-10), bloquea a los `lock_after` consecutivos, emite
  `LoginAttempted` y confirma antes del 401 (S2-D8); todo 401 se alarga hasta el piso
  `min_duration_ms` (S2-D39). Un éxito purga los refresh vencidos hace más de 30 días (L-4).
- `refresh`: `SELECT ... FOR UPDATE` (usuario y luego token), reuso real solo fuera de la
  gracia (M-2: revoca todo, fija `tokens_valid_after`, emite `SessionsRevoked` y confirma
  antes del 401), tope absoluto de la familia (L-4) y rotación que hereda `family_started_at`.
- `logout` por la cookie (H-1): revoca solo ese refresh, sin `replaced_by_id`.
- `configure_sleeper` y `wait_floor`: la espera del piso es inyectable (las pruebas la
  sustituyen por un espía que no duerme); `links.forgot` usa el mismo piso.
Los logs nunca llevan el correo tecleado ni la clave del límite. argon2 corre en
`anyio.to_thread.run_sync`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
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
    verify_password,
)
from app.modules.auth import rules, tokens
from app.modules.auth.events import (
    LoginAttempted,
    LoginFailureReason,
    SessionsRevoked,
    UserLocked,
)
from app.modules.auth.exceptions import (
    InvalidCredentials,
    InvalidRefresh,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import (
    AUTH_FILTER,
    AuthPolicy,
    account_may_authenticate,
    is_active_admin,
    is_refresh_usable,
    is_reuse,
    normalize_login_email,
    should_auto_lock,
    truncate,
    user_status,
)
from app.modules.auth.schemas import (
    UserSummary,
)

logger = logging.getLogger("app.auth")


USER_AGENT_EVENT_MAX: Final = 120  # L-8: el evento guarda el agente truncado


USER_AGENT_ROW_MAX: Final = 255  # columna `refresh_tokens.user_agent`


PURGE_EXPIRED_AFTER: Final = timedelta(days=30)  # L-4: purga oportunista en cada login


ACCOUNT_BUCKET: Final = "login-account"


ACCOUNT_GLOBAL_BUCKET: Final = "login-account-global"


ACCOUNT_IPV4_PREFIX: Final = 32  # N-3 (revisión V10): antes /24 (E9)


_REASON_BY_STATUS: Final[dict[str, LoginFailureReason]] = {
    "locked": "locked",
    "inactive": "inactive",
    "pending_activation": "pending",
}


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


# Principal -----------------------------------------------------------------------------------


async def _active_admin_count(session: AsyncSession) -> int:
    total = await session.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", AUTH_FILTER)
    )
    return int(total or 0)


async def load_active_principal(session: AsyncSession, user_id: UUID) -> Principal | None:
    """El `PrincipalLoader` de `current_user`: estado vigente o `None` (M-7, H-3)."""
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
        usuario.role,
        usuario.member_id,
        must_change_password=usuario.must_change_password,
        tokens_valid_after=usuario.tokens_valid_after,
    )


# Login ---------------------------------------------------------------------------------------


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


@dataclass(frozen=True)
class _Reservation:
    """Marcas de la reserva de cupo por cuenta y global (revisión Python M2)."""

    account: float
    email: float


async def _reserve_account_limits(keys: _LoginKeys, policy: AuthPolicy) -> _Reservation:
    """Reserva el cupo por cuenta y el global ANTES de argon2 (429 sin verificar). Si el global
    no tiene cupo se devuelve el de la cuenta: un 429 no consume nada."""
    cuenta = await ratelimit.reserve(
        ACCOUNT_BUCKET, keys.account, limit=policy.account_limit, window_s=policy.account_window_s
    )
    try:
        del_correo = await ratelimit.reserve(
            ACCOUNT_GLOBAL_BUCKET,
            keys.email,
            limit=policy.account_global_limit,
            window_s=policy.account_global_window_s,
            kind="account-global",
        )
    except BaseException:
        await ratelimit.release(ACCOUNT_BUCKET, keys.account, cuenta)
        raise
    return _Reservation(account=cuenta, email=del_correo)


async def _release_account_limits(keys: _LoginKeys, reservation: _Reservation) -> None:
    """Un login correcto devuelve el cupo: solo los fallos cuentan (H-4)."""
    await ratelimit.release(ACCOUNT_BUCKET, keys.account, reservation.account)
    await ratelimit.release(
        ACCOUNT_GLOBAL_BUCKET, keys.email, reservation.email, kind="account-global"
    )


async def verify_password_or_dummy(user: User | None, password: str) -> bool:
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


async def wait_floor(started: float, policy: AuthPolicy) -> None:
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
    acceso = create_access_token(user.id, user.role, user.member_id, current_clock())
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
    """US-042: sesión nueva o `InvalidCredentials`/`TooManyRequestsError` (ver el módulo)."""
    inicio = time.monotonic()
    correo = normalize_login_email(email)
    # N-3: IPv4 exacta (o /64), como `rate_limit`; con /24 un equipo de la LAN negaba el login.
    red = ratelimit.ip_bucket_key(ip, ipv4_prefix=ACCOUNT_IPV4_PREFIX)
    claves = _LoginKeys(account=f"{correo}|{red}", email=correo)
    usuario = await _find_login_user(session, correo)
    exento = await _is_exempt(session, usuario)
    # M2: reserva atómica antes de argon2 (429 sin verificar); el éxito la devuelve.
    reserva = None if exento else await _reserve_account_limits(claves, policy)
    correcta = await verify_password_or_dummy(usuario, password)
    if usuario is not None and correcta and account_may_authenticate(usuario):
        resultado = await _issue_session(
            session, usuario, password, ip=ip, user_agent=user_agent, policy=policy
        )
        if reserva is not None:
            await _release_account_limits(claves, reserva)
        return resultado
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
    await wait_floor(inicio, policy)
    raise InvalidCredentials()


# Refresh y logout ----------------------------------------------------------------------------


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
    """US-043: rota el refresh de la cookie o lanza `InvalidRefresh` (M-2, L-4)."""
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
    acceso = create_access_token(usuario.id, usuario.role, usuario.member_id, current_clock())
    return RefreshResult(access_token=acceso, expires_in=policy.access_ttl_s, refresh_token=claro)


async def logout(session: AsyncSession, token: str | None) -> None:
    """H-1: revoca solo el refresh de la cookie; sin token, desconocido o ya revocado, nada."""
    fila = await _locked_refresh_row(session, token)
    if fila is None or fila.revoked_at is not None:
        return
    with actor_scope(fila.user_id):
        fila.revoked_at = current_clock().now_utc()
        await session.flush()
