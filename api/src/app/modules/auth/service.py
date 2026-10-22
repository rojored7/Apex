"""Service de auth (US-041; adaptador del puerto `PrincipalLoader` de US-034).

- Puras: `validate_user_role` (S7: `member` exige `member_id`; `admin`/`coach` no lo llevan
  en v0.1), `normalize_login_email`, `is_active_admin`, `user_status`,
  `validate_password_policy` (delegada a `core.security`, traducida a `AuthError` 422).
- `seed_admin`: crea el primer admin activo si no hay otro (el usuario técnico no cuenta:
  `is_active = false`), audita sin el hash (`__audit_redact__`) y emite `UserCreated`.
- `load_active_principal`: el cargador real de `current_user`. Devuelve `None` si el usuario no
  existe, está inactivo, bloqueado, dado de baja, sin contraseña o es `SYSTEM_USER_ID`. Se
  registra al importarse el módulo (`load_module_services` en `create_app`).
- `names_for`, `ids_by_email`, `active_admin_id_by_email`: lecturas para auditoría (US-110) y
  para `--as <email>` del CLI (N-15).
`hash_password` cuesta CPU: se envuelve en `anyio.to_thread.run_sync`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import SYSTEM_USER_ID
from app.core.events import DomainEvent
from app.core.security import (
    Principal,
    WeakPasswordError,
    hash_password,
    register_principal_loader,
    verify_password,
)
from app.core.security import validate_password_policy as _core_password_policy
from app.modules.auth.exceptions import AuthError
from app.modules.auth.models import User
from app.modules.auth.schemas import Role, UserStatus

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


def user_status(user: User) -> UserStatus:
    if user.deleted_at is not None:
        return "deleted"
    if user.locked_at is not None:
        return "locked"
    if not user.is_active:
        return "inactive"
    return "active"


def is_active_admin(user: User) -> bool:
    return user.role == "admin" and user_status(user) == "active" and user.password_hash is not None


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


# Casos de uso -----------------------------------------------------------------------------


async def _active_admin(session: AsyncSession) -> User | None:
    filas = await session.scalars(
        select(User).where(
            User.role == "admin",
            User.is_active.is_(True),
            User.locked_at.is_(None),
            User.deleted_at.is_(None),
            User.password_hash.is_not(None),
            User.id != SYSTEM_USER_ID,
        )
    )
    return filas.first()


async def seed_admin(session: AsyncSession, email: str, password: str, *, by: UUID) -> SeedResult:
    existente = await _active_admin(session)
    if existente is not None:
        return SeedResult("skipped", existente.id)
    validate_password_policy(password)
    correo = normalize_login_email(email)
    hashed = await anyio.to_thread.run_sync(hash_password, password)
    usuario = User(email=correo, password_hash=hashed, role="admin", member_id=None, created_by=by)
    session.add(usuario)
    await session.flush()
    await events.emit(UserCreated(user_id=usuario.id, role="admin", by=by), session)
    return SeedResult("created", usuario.id)


async def load_active_principal(session: AsyncSession, user_id: UUID) -> Principal | None:
    if user_id == SYSTEM_USER_ID:
        return None
    usuario = await session.get(User, user_id)
    if usuario is None or user_status(usuario) != "active" or usuario.password_hash is None:
        return None
    return Principal(usuario.id, usuario.role, usuario.member_id)  # type: ignore[arg-type]


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


async def active_admin_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    """Id de una persona viva con ese correo (cualquier rol, no dada de baja), para `--as`."""
    return (await ids_by_email(session, [email])).get(normalize_login_email(email))


register_principal_loader(load_active_principal)
