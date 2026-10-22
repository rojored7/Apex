"""Ayudas de las pruebas de "Mi cuenta" y usuarios (S2-B3; US-045, US-046, US-047).

- Rutas (`ME`, `PASSWORD`, `USERS`) y la contraseña nueva válida de las pruebas (`NUEVA`).
- `avanzar(reloj, segundos)`: `FrozenClock.advance` no acepta segundos; el corte de H-3 se
  compara en segundos enteros, así que las pruebas mueven el reloj al menos 1 s entre el
  access viejo y el cambio de contraseña.
- `fila_usuario`, `filas_refresh`, `tokens_de` y `filas_auditoria`: leen la base con SQL o
  `select` propio, sin depender de lo que el service devuelva.
- `etiqueta()`: sufijo único para aislar los correos de una prueba (`q` lo filtra).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEntry
from app.core.clock import FrozenClock
from app.modules.auth.models import OneTimeToken, RefreshToken

ME = "/api/v1/auth/me"
PASSWORD = "/api/v1/auth/me/password"  # noqa: S105 - ruta, no un secreto
USERS = "/api/v1/users"
# Cumple la política (12 a 128, no común) y es distinta de `CLAVE_PRUEBA`.
NUEVA = "Mandarina-Solar-58q"
CAMPOS_USER_ROW = {
    "id",
    "email",
    "role",
    "status",
    "member_id",
    "last_login_at",
    "created_at",
    "active_sessions",
}
CAMPOS_USER_OUT = {"id", "email", "role", "member_id", "status", "must_change_password"}


def avanzar(reloj: FrozenClock, segundos: float) -> None:
    reloj.set(reloj.now_utc() + timedelta(seconds=segundos))


def etiqueta() -> str:
    return uuid4().hex[:8]


async def fila_usuario(session: AsyncSession, user_id: UUID) -> dict[str, Any]:
    fila = (
        await session.execute(
            text(
                "SELECT email, password_hash, role, member_id, is_active, locked_at, "
                "deleted_at, must_change_password, failed_login_count, tokens_valid_after, "
                "created_by FROM auth.users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).one()
    return dict(fila._mapping)


async def filas_refresh(session: AsyncSession, user_id: UUID) -> list[RefreshToken]:
    filas = await session.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .order_by(RefreshToken.created_at, RefreshToken.id)
        .execution_options(populate_existing=True)
    )
    return list(filas.all())


async def tokens_de(session: AsyncSession, user_id: UUID) -> list[OneTimeToken]:
    filas = await session.scalars(
        select(OneTimeToken)
        .where(OneTimeToken.user_id == user_id)
        .order_by(OneTimeToken.created_at, OneTimeToken.id)
        .execution_options(populate_existing=True)
    )
    return list(filas.all())


async def filas_auditoria(
    session: AsyncSession, tabla: str, record_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Filas de `audit.audit_log` de `tabla` (y del registro, si se pide), en orden."""
    t = AuditEntry.__table__
    consulta = select(t).where(t.c.table_name == tabla).order_by(t.c.seq)
    if record_id is not None:
        consulta = consulta.where(t.c.record_id == record_id)
    return [dict(f) for f in (await session.execute(consulta)).mappings().all()]
