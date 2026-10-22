"""Operaciones de sesión con base (S2-B2; S2-D4, privado del módulo auth).

- `revoke_all`: un `UPDATE` masivo de `refresh_tokens` (no auditada) que además fija
  `auth.users.tokens_valid_after` al instante truncado a segundos (H-3, E8): los access con
  `iat` anterior dejan de valer en la siguiente petición.
- `commit_failure`: flush y commit antes de lanzar un 401 (S2-D8): el contador, el bloqueo, los
  eventos y la auditoría sobreviven al rollback de `get_session`.
- `purge_expired_for_user`: borra los refresh del usuario vencidos hace más de `older_than`
  (L-4), salvo los que un refresh más nuevo aún vigente referencia por `replaced_by_id`.
- `increment_failures`: `UPDATE ... RETURNING failed_login_count` atómico (L-10); la columna
  está en `__audit_exclude__`, así que saltarse el hook no pierde auditoría.
- `issue_one_time_token` (S2-B3, blueprint 7.2): cierra por ORM (`used_at = now`, queda el
  `update` auditado) los tokens abiertos del mismo usuario y propósito, crea el nuevo con
  `expires_at = now + ACTIVATE_TTL | RESET_TTL` y solo su `hash_opaque_token`; devuelve el token
  en claro, que nunca se guarda ni se registra.
- `get_alive_or_404` (S2-B4): el usuario o `UserNotFound` (técnico, inexistente y, sin
  `include_deleted`, borrado); `for_update` bloquea la fila del usuario.
- `close_open_one_time_tokens` (revisión S2-B4, MEDIUM-1): cierra por ORM todos los enlaces
  abiertos del usuario tras fijar o cambiar su contraseña.
Orden de candados en todo el módulo: usuario → tokens de un solo uso.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.context import SYSTEM_USER_ID, get_actor
from app.core.security import hash_opaque_token, new_opaque_token
from app.modules.auth.exceptions import UserNotFound
from app.modules.auth.models import OneTimeToken, RefreshToken, User
from app.modules.auth.rules import ACTIVATE_TTL, RESET_TTL

OneTimePurpose = Literal["activate", "reset"]


def cutoff_of(now: datetime) -> datetime:
    """`tokens_valid_after`: el instante truncado a segundos (el `iat` del JWT es entero)."""
    return now.replace(microsecond=0)


async def revoke_all(
    session: AsyncSession, user_id: UUID, *, now: datetime, except_id: UUID | None = None
) -> int:
    condiciones = [
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    ]
    if except_id is not None:
        condiciones.append(RefreshToken.id != except_id)
    resultado = await session.execute(
        update(RefreshToken)
        .where(*condiciones)
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(tokens_valid_after=cutoff_of(now))
        .execution_options(synchronize_session=False)
    )
    return int(getattr(resultado, "rowcount", 0) or 0)


async def commit_failure(session: AsyncSession) -> None:
    await session.flush()
    await session.commit()


async def purge_expired_for_user(
    session: AsyncSession, user_id: UUID, *, now: datetime, older_than: timedelta
) -> int:
    limite = now - older_than
    sucesor = aliased(RefreshToken)
    referenciado_por_vigente = exists(
        select(sucesor.id).where(
            sucesor.replaced_by_id == RefreshToken.id, sucesor.expires_at >= limite
        )
    )
    resultado = await session.execute(
        delete(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at < limite,
            ~referenciado_por_vigente,
        )
        .execution_options(synchronize_session=False)
    )
    return int(getattr(resultado, "rowcount", 0) or 0)


async def increment_failures(session: AsyncSession, user_id: UUID) -> int:
    valor = await session.scalar(
        update(User)
        .where(User.id == user_id)
        .values(failed_login_count=User.failed_login_count + 1)
        .returning(User.failed_login_count)
        .execution_options(synchronize_session=False)
    )
    return int(valor or 0)


async def record_success(session: AsyncSession, user_id: UUID, *, now: datetime) -> None:
    """Login correcto: `last_login_at = now` y el contador consecutivo a 0 (S2-D10). Ambas
    columnas están fuera de la auditoría; la fila `login` la deja `LoginAttempted`."""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(last_login_at=now, failed_login_count=0)
        .execution_options(synchronize_session=False)
    )


_TTL_BY_PURPOSE: Final[dict[str, timedelta]] = {"activate": ACTIVATE_TTL, "reset": RESET_TTL}


async def issue_one_time_token(
    session: AsyncSession, user_id: UUID, purpose: OneTimePurpose, *, now: datetime
) -> tuple[str, OneTimeToken]:
    """A lo sumo un token abierto por usuario y propósito. `created_by` es el actor vigente
    (`get_actor`): quien crea la cuenta o pide el enlace; la auditoría lo exige igual."""
    actor = get_actor()
    abiertos = await session.scalars(
        select(OneTimeToken)
        .where(
            OneTimeToken.user_id == user_id,
            OneTimeToken.purpose == purpose,
            OneTimeToken.used_at.is_(None),
        )
        .with_for_update()
    )
    for anterior in abiertos.all():
        anterior.used_at = now  # por ORM: queda el `update` auditado
    claro = new_opaque_token()
    fila = OneTimeToken(
        user_id=user_id,
        token_hash=hash_opaque_token(claro),
        purpose=purpose,
        expires_at=now + _TTL_BY_PURPOSE[purpose],
        created_by=actor,
    )
    session.add(fila)
    await session.flush()
    return claro, fila


async def close_open_one_time_tokens(session: AsyncSession, user_id: UUID, *, now: datetime) -> int:
    """Cierra por ORM (`used_at = now`, `update` auditado) todos los enlaces abiertos del
    usuario, de cualquier propósito: tras fijar o cambiar la contraseña ninguno debe servir."""
    abiertos = await session.scalars(
        select(OneTimeToken)
        .where(OneTimeToken.user_id == user_id, OneTimeToken.used_at.is_(None))
        .with_for_update()
    )
    cerrados = 0
    for abierto in abiertos.all():
        abierto.used_at = now
        cerrados += 1
    await session.flush()
    return cerrados


async def get_alive_or_404(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_deleted: bool = False,
    for_update: bool = False,
) -> User:
    """El usuario leído fresco de la base (S2-B4). El técnico (`SYSTEM_USER_ID`) y los
    inexistentes dan `UserNotFound`; un borrado también, salvo con `include_deleted=True`.
    `for_update` serializa dos emisiones de enlace sobre la misma cuenta."""
    if user_id == SYSTEM_USER_ID:
        raise UserNotFound()
    consulta = select(User).where(User.id == user_id)
    if not include_deleted:
        consulta = consulta.where(User.deleted_at.is_(None))
    if for_update:
        consulta = consulta.with_for_update()
    usuario = await session.scalar(consulta.execution_options(populate_existing=True))
    if usuario is None:
        raise UserNotFound()
    return usuario
