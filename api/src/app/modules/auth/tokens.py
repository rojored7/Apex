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
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.auth.models import RefreshToken, User


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
