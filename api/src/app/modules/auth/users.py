"""Cuentas: seed, lecturas para otros módulos, "Mi cuenta" y el ciclo de vida del usuario
(US-041, S2-B3: US-045, US-046, US-047; S2-B5: US-049, US-050, US-051). Privado del módulo
(revisión Python H1); se usa a través de `auth.service`.

- `validate_user_role` (S7: `member` exige `member_id`; `admin`/`coach` no lo llevan en v0.1)
  y `validate_password_policy` (la de `rules`, con `field="password"`; seed y CLI).
- `seed_admin(force_change=True)`: el primer admin activo si no hay otro (el técnico no
  cuenta), con `must_change_password` (M-8); emite `UserCreated`.
- `names_for`, `ids_by_email`, `active_user_id_by_email`, `active_admin_id_by_email`: lecturas
  para la auditoría (US-110) y el `--as` del CLI (N-15; solo cuentas `active`, L-4 del Sprint 1).
- `me` (S2-D14: el usuario y `settings.service.gym_name`) y `change_password` (US-046; H-3,
  S2-D37; revisión Python M1: los tres argon2 corren sin candado y el `FOR UPDATE` final exige
  que el hash no haya cambiado).
- `list_users` (sin el técnico, `q` escapado con `core.search`, orden por correo,
  `active_sessions`) y `create_user` (admin o coach sin hash, token `activate` de 72 h,
  `EmailTaken`; L-2).
- `get_user`, `update_user` (correo único entre vivos, rol con `validate_user_role` y
  `LastAdmin`; N-8: el correo de otro admin activo no se cambia), `delete_user`, `lock`,
  `unlock` y `revoke_sessions`. Candados siempre en el orden admins → usuario → tokens.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import Final, Literal
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events, ratelimit
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID
from app.core.db import violated_constraint
from app.core.errors import UnauthorizedError
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, contains_pattern
from app.core.security import (
    SESSION_INVALID_MESSAGE,
    Principal,
    TokenInvalid,
    create_access_token,
    hash_opaque_token,
    hash_password,
)
from app.modules.auth import rules, tokens
from app.modules.auth.events import (
    PasswordChanged,
    SessionsRevoked,
    UserCreated,
    UserLocked,
)
from app.modules.auth.exceptions import (
    AuthError,
    EmailTaken,
    InvalidCurrentPassword,
    LastAdmin,
    NotLocked,
    UserNotEligible,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rules import (
    AUTH_FILTER,
    AuthPolicy,
    is_active_admin,
    normalize_login_email,
)
from app.modules.auth.schemas import (
    AccessTokenOut,
    CreateUserOut,
    MeOut,
    Role,
    StaffRole,
    UserRow,
    UserStatus,
)
from app.modules.auth.sessions import (
    ACCOUNT_BUCKET,
    ACCOUNT_GLOBAL_BUCKET,
    verify_password_or_dummy,
)

# Arista `auth → settings` del grafo de services (S2-D53): import a nivel de módulo.
from app.modules.settings import service as settings_service

logger = logging.getLogger("app.auth")


EMAIL_ALIVE_INDEX: Final = "uq_users_email_alive"


# Fallos de la contraseña actual en `POST /auth/me/password`, por usuario (revisión S2-B3).
CHANGE_PASSWORD_BUCKET: Final = "change-password-user"  # noqa: S105 - nombre de bucket


CHANGE_PASSWORD_USER_LIMIT: Final = 5


CHANGE_PASSWORD_USER_WINDOW_S: Final = 900


SeedOutcome = Literal["created", "skipped"]


@dataclass(frozen=True)
class SeedResult:
    outcome: SeedOutcome
    user_id: UUID | None


# Puras ---------------------------------------------------------------------------------------


def validate_user_role(role: Role, member_id: UUID | None) -> None:
    """S7: `member` exige `member_id`; `admin` y `coach` no lo llevan (`AuthError` 422)."""
    if role == "member" and member_id is None:
        raise AuthError("member_id_required", "Un socio necesita su ficha.", field="member_id")
    if role != "member" and member_id is not None:
        raise AuthError(
            "member_id_not_allowed", "Admin y coach no llevan ficha de socio.", field="member_id"
        )


def validate_password_policy(password: str, *, current_hash: str | None = None) -> None:
    """La de `rules` con `field="password"` (seed y CLI); cambio y reset usan `new_password`."""
    rules.validate_password_policy(password, current_hash=current_hash)


# Lecturas para otros módulos -----------------------------------------------------------------


async def _active_admin(session: AsyncSession) -> User | None:
    filas = await session.scalars(select(User).where(User.role == "admin", AUTH_FILTER))
    return filas.first()


async def names_for(session: AsyncSession, user_ids: Sequence[UUID]) -> dict[UUID, str]:
    """Correo por id (los usuarios no tienen nombre; US-110)."""
    if not user_ids:
        return {}
    filas = await session.execute(select(User.id, User.email).where(User.id.in_(list(user_ids))))
    return {fila.id: fila.email for fila in filas}


async def ids_by_email(session: AsyncSession, emails: Sequence[str]) -> dict[str, UUID]:
    """Id de cada correo (normalizado) con una cuenta no borrada."""
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


async def active_admin_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    """Id de un admin en estado `active` (para el `--as` de `cli issue-reset-link`)."""
    return await session.scalar(
        select(User.id).where(
            User.email == normalize_login_email(email), User.role == "admin", AUTH_FILTER
        )
    )


# Seed ----------------------------------------------------------------------------------------


async def seed_admin(
    session: AsyncSession, email: str, password: str, *, by: UUID, force_change: bool = True
) -> SeedResult:
    """El primer admin activo (M-8: debe cambiar la contraseña); `skipped` si ya hay uno."""
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


# Mi cuenta (S2-B3) ---------------------------------------------------------------------------


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


async def _verified_current_hash(
    session: AsyncSession, user_id: UUID, current_password: str
) -> str | None:
    """El hash vigente si `current_password` lo verifica; si no, suma un fallo al tope por
    usuario y lanza `InvalidCurrentPassword`. Lee SIN candado (revisión Python M1)."""
    clave = str(user_id)
    await ratelimit.enforce(  # antes de argon2 y sin sumar (como el límite por cuenta)
        CHANGE_PASSWORD_BUCKET,
        clave,
        limit=CHANGE_PASSWORD_USER_LIMIT,
        window_s=CHANGE_PASSWORD_USER_WINDOW_S,
        kind="user",
        count=False,
    )
    usuario = await _fresh_user(session, user_id)
    if not await verify_password_or_dummy(usuario, current_password) or usuario is None:
        await ratelimit.record(
            CHANGE_PASSWORD_BUCKET, clave, window_s=CHANGE_PASSWORD_USER_WINDOW_S, kind="user"
        )
        logger.info("cambio de contraseña rechazado", extra={"user_id": clave})
        raise InvalidCurrentPassword(field="current_password")
    return usuario.password_hash


async def _locked_if_unchanged(session: AsyncSession, user_id: UUID, hash_read: str | None) -> User:
    """`FOR UPDATE` de la cuenta tras argon2 (M1). Si otro cambio ganó la carrera, la "actual"
    que tecleó ya no lo es: `InvalidCurrentPassword` sin sumar al tope (no es un intento de
    adivinar) y sin tocar nada."""
    usuario = await _fresh_user(session, user_id, for_update=True)
    if usuario is None or usuario.password_hash != hash_read:
        logger.info("cambio de contraseña concurrente rechazado", extra={"user_id": str(user_id)})
        raise InvalidCurrentPassword(field="current_password")
    return usuario


async def change_password(
    session: AsyncSession,
    user_id: UUID,
    current_password: str,
    new_password: str,
    *,
    current_refresh: str | None,
    policy: AuthPolicy,
) -> AccessTokenOut:
    """US-046 (H-3, S2-D37, M-8; revisión Python M1): actual, política, hash nuevo, corte y
    access nuevo.

    Orden fijo: la actual primero (`InvalidCurrentPassword`), luego la política con
    `field="new_password"` (incluida "distinta de la actual"). Los tres argon2 corren sin
    candado; el `FOR UPDATE` llega al final y exige que el hash no haya cambiado. Un solo
    `update` auditado de `auth.users`; `revoke_all` deja viva la sesión de la cookie y fija
    `tokens_valid_after` aunque no haya otras sesiones.
    """
    hash_leido = await _verified_current_hash(session, user_id, current_password)
    await anyio.to_thread.run_sync(
        partial(
            rules.validate_password_policy,
            new_password,
            current_hash=hash_leido,
            field="new_password",
        )
    )
    nuevo_hash = await anyio.to_thread.run_sync(hash_password, new_password)
    usuario = await _locked_if_unchanged(session, user_id, hash_leido)
    revocadas = await _store_new_password(session, usuario, nuevo_hash, current_refresh)
    logger.info(
        "contraseña cambiada", extra={"user_id": str(user_id), "sesiones_revocadas": revocadas}
    )
    acceso = create_access_token(usuario.id, usuario.role, usuario.member_id, current_clock())
    return AccessTokenOut(access_token=acceso, expires_in=policy.access_ttl_s)


async def _store_new_password(
    session: AsyncSession, usuario: User, nuevo_hash: str, current_refresh: str | None
) -> int:
    """El `update` auditado, el cierre de enlaces, el corte de sesiones (salvo la de la cookie)
    y los eventos de `change_password`; devuelve cuántas sesiones revocó."""
    now = current_clock().now_utc()
    usuario.password_hash = nuevo_hash
    usuario.must_change_password = False
    usuario.failed_login_count = 0
    await session.flush()
    # Revisión S2-B4 (MEDIUM-1): un enlace abierto no sobrevive al cambio de contraseña.
    await tokens.close_open_one_time_tokens(session, usuario.id, now=now)
    conservar = await _own_refresh_id(session, usuario.id, current_refresh)
    revocadas = await tokens.revoke_all(session, usuario.id, now=now, except_id=conservar)
    await events.emit(
        PasswordChanged(user_id=usuario.id, by=usuario.id, via="change", via_link_issued_by=None),
        session,
    )
    if revocadas:
        await events.emit(
            SessionsRevoked(
                user_id=usuario.id, by=usuario.id, revoked=revocadas, reason="password_changed"
            ),
            session,
        )
    return revocadas


# Lista y alta (S2-B3) ------------------------------------------------------------------------


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
        patron = contains_pattern(q)  # valor ligado, nunca texto SQL (core/search, H3)
        consulta = consulta.where(User.email.ilike(patron, escape=LIKE_ESCAPE))
    usuarios, total = await paginate(session, consulta.order_by(User.email.asc()), page)
    sesiones = await _active_sessions(session, [u.id for u in usuarios])
    filas = [rules.user_row(u, active_sessions=sesiones.get(u.id, 0)) for u in usuarios]
    return to_page(filas, total, page)


async def _alive_user_id(session: AsyncSession, email: str) -> UUID | None:
    return await session.scalar(
        select(User.id).where(User.email == email, User.deleted_at.is_(None))
    )


def _is_email_conflict(error: IntegrityError) -> bool:
    return violated_constraint(error) == EMAIL_ALIVE_INDEX


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


# Ciclo de vida (S2-B5) -----------------------------------------------------------------------


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
    if nuevo_correo is not None and usuario.id != by and is_active_admin(usuario):
        # N-8 (L-13 en el correo): redirigir el correo de otro admin activo sería tomar su
        # cuenta en cuanto `forgot` envíe enlaces (US-131). El propio admin sí puede.
        logger.info("cambio de correo rechazado por L-13", extra={"user_id": str(usuario.id)})
        raise UserNotEligible()
    if nuevo_rol is not None:
        _check_role_change(usuario, nuevo_rol, admins)
    if nuevo_correo is not None:
        await _check_email_free(session, usuario, nuevo_correo)
    if nuevo_rol is None and nuevo_correo is None:
        return usuario
    await _apply_user_changes(session, usuario, nuevo_rol, nuevo_correo)
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


async def _apply_user_changes(
    session: AsyncSession, usuario: User, nuevo_rol: Role | None, nuevo_correo: str | None
) -> None:
    """Rol y correo en un `begin_nested()`: la carrera del correo la decide
    `uq_users_email_alive` (`EmailTaken` con el ganador). Un correo nuevo cierra los enlaces
    abiertos (revisión S2-B5, LOW-3: un enlace entregado al correo anterior deja de servir)."""
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
        await tokens.close_open_one_time_tokens(session, usuario.id, now=current_clock().now_utc())


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
