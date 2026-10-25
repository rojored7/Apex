"""Ayudas de las pruebas de membresías (plan del Sprint 3, sección 2, bloque B1).

- `MEMBERSHIPS` y `ruta_venta(member_id)`: rutas del api.
- `cuerpo_venta(plan_id, **cambios)`: cuerpo JSON de `POST /members/{member_id}/memberships`.
- `CAMPOS_MEMBERSHIP` y `CAMPOS_SELL`: las claves exactas de `MembershipOut` y
  `SellMembershipOut`.
- `vender(session, actor, **datos)`: `service.sell` bajo `actor_scope(actor)` y commit (una
  petición, una transacción; con la `session` de savepoint libera el savepoint).
- Lecturas con SQL crudo: `leer_membresia`, `membresias_del_socio`, `leer_auditoria` y
  `contar_decrypt` (filas de `crypto.crypto_ops` con ese `record_id`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.memberships import service
from app.modules.memberships.schemas import SellMembershipOut

MEMBERSHIPS = "/api/v1/memberships"

CAMPOS_MEMBERSHIP = frozenset(
    {
        "id",
        "member_id",
        "member_name",
        "plan_id",
        "plan_name",
        "agreed_price_cop",
        "paid_cop",
        "start_date",
        "end_date",
        "classes_total",
        "classes_remaining",
        "status",
        "freezes",
        "cancel_reason",
        "cancelled_at",
        "created_at",
    }
)
CAMPOS_SELL = CAMPOS_MEMBERSHIP | {"first_payment_id"}


def ruta_venta(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/memberships"


def cuerpo_venta(plan_id: UUID | str, **cambios: Any) -> dict[str, Any]:
    """Cuerpo de la venta: solo `plan_id` y lo que se pida (`start_date`, `renew`, ...)."""
    return {"plan_id": str(plan_id), **cambios}


async def vender(session: AsyncSession, actor: UUID, **datos: Any) -> SellMembershipOut:
    with actor_scope(actor):
        salida = await service.sell(session, **datos)
        await session.commit()
    return salida


_COLUMNAS = (
    "id, member_id, plan_id, agreed_price_cop, start_date, end_date, classes_total, "
    "classes_remaining, status, cancel_reason, cancelled_by, cancelled_at, created_by"
)
_LEER_MEMBRESIA = text(f"SELECT {_COLUMNAS} FROM memberships.memberships WHERE id = :id")  # noqa: S608
_DEL_SOCIO = text(
    f"SELECT {_COLUMNAS} FROM memberships.memberships WHERE member_id = :m ORDER BY start_date"  # noqa: S608
)


async def leer_membresia(session: AsyncSession, membership_id: UUID) -> dict[str, Any] | None:
    fila = (await session.execute(_LEER_MEMBRESIA, {"id": membership_id})).mappings().first()
    return dict(fila) if fila is not None else None


async def membresias_del_socio(session: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    filas = (await session.execute(_DEL_SOCIO, {"m": member_id})).mappings().all()
    return [dict(f) for f in filas]


async def leer_auditoria(
    session: AsyncSession, table_name: str, record_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Filas de `audit.audit_log` de la tabla (y del registro, si se da), en orden de `seq`."""
    sql = (
        "SELECT action, table_name, record_id, subject_member_id, user_id, after "
        "FROM audit.audit_log WHERE table_name = :t"
    )
    parametros: dict[str, Any] = {"t": table_name}
    if record_id is not None:
        sql += " AND record_id = :r"
        parametros["r"] = record_id
    filas = (await session.execute(text(sql + " ORDER BY seq"), parametros)).mappings().all()
    return [dict(f) for f in filas]


async def contar_decrypt(session: AsyncSession, record_id: UUID) -> int:
    consulta = text(
        "SELECT count(*) FROM crypto.crypto_ops WHERE verb = 'decrypt' AND record_id = :r"
    )
    return int(await session.scalar(consulta, {"r": record_id}) or 0)
