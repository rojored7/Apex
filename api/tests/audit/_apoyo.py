"""Apoyo de las pruebas de la verificación de la cadena (plan del Sprint 4A, sección 2, bloque B3).

- `VERIFY = "/api/v1/audit/verify"` y `VERIFY_LAST`; `CAMPOS_RESULTADO` (forma exacta de
  `VerifyResultOut`) y `CLAVES_AFTER` (las de la fila `verify` de la cadena, S4A-D12 y S4A-D43).
- `candado_libre(url)`: desde una conexión asyncpg independiente (otro proceso, para PostgreSQL),
  `pg_try_advisory_lock(4_270_003)`; si lo obtiene lo suelta y devuelve `True`. Así una prueba
  sabe que ninguna conexión (tampoco una devuelta al pool) se quedó con el candado.
- `EspiaDeConexiones`: envuelve `AsyncConnection.execution_options` e `invalidate` a nivel de
  clase y anota qué conexiones pasaron a `AUTOCOMMIT` y cuáles se invalidaron (H-2, S4A-D44).

Bloque B4 (lista y detalle; lo reutilizan B5 y B8):
- `AUDIT = "/api/v1/audit"`, `ruta_entrada(seq)`; `CAMPOS_ROW` (forma exacta de `AuditRow`),
  `CAMPOS_DETAIL` y `CAMPOS_CHANGE`; `ANA_EMAIL`/`JUAN_EMAIL` y sus partes locales.
- `leer_entrada(session, seq)`: la fila cruda de `audit.audit_log` (o `None`).
- `filas_de(session, **filtros)`: filas crudas con igualdad en cada columna, en orden de `seq`.
- `sembrar_actividad(session, *, ana, juan) -> Actividad`: por los services reales y cada paso
  como una petición (sesión vacía, `actor_scope` del usuario y `commit`): Ana (admin) crea el
  plan "Mensual Auditoría" y la socia Lucía (`tests.members._apoyo.entrada()`); Juan (coach)
  le cambia teléfono y correo y revela el teléfono; Ana vende el plan sin pago (queda
  `pending_payment`); Juan registra un pago de 120.000 en efectivo (activa la membresía) y Ana lo
  anula. Devuelve los ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.audit_verify import AUDIT_VERIFY_LOCK_KEY
from app.core.context import actor_scope
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberPatch
from app.modules.memberships import service as memberships_service
from app.modules.payments import service as payments_service
from app.modules.plans import service as plans_service
from app.modules.plans.schemas import PlanCreate
from tests.members._apoyo import entrada

VERIFY: Final = "/api/v1/audit/verify"
VERIFY_LAST: Final = "/api/v1/audit/verify/last"
CAMPOS_RESULTADO: Final = frozenset(
    {
        "ok",
        "rows_checked",
        "through_seq",
        "broken_at_seq",
        "started_at",
        "finished_at",
        "triggered_by",
        "source",
    }
)
CLAVES_AFTER: Final = frozenset(
    {
        "ok",
        "rows_checked",
        "broken_at_seq",
        "through_seq",
        "through_hash",
        "started_at",
        "finished_at",
        "source",
    }
)


def dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def candado_libre(url: str) -> bool:
    """`True` si una conexión independiente obtiene (y suelta) el candado `4_270_003`."""
    conexion = await asyncpg.connect(dsn(url))
    try:
        obtenido = bool(
            await conexion.fetchval("SELECT pg_try_advisory_lock($1)", AUDIT_VERIFY_LOCK_KEY)
        )
        if obtenido:
            await conexion.fetchval("SELECT pg_advisory_unlock($1)", AUDIT_VERIFY_LOCK_KEY)
        return obtenido
    finally:
        await conexion.close()


@dataclass
class EspiaDeConexiones:
    """Conexiones (por `id`) que pidieron `AUTOCOMMIT` y que se invalidaron."""

    autocommit: list[int] = field(default_factory=list)
    invalidadas: list[int] = field(default_factory=list)

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> EspiaDeConexiones:
        original_opciones = AsyncConnection.execution_options
        original_invalidar = AsyncConnection.invalidate
        espia = self

        async def opciones(conn: AsyncConnection, **opt: Any) -> AsyncConnection:
            if opt.get("isolation_level") == "AUTOCOMMIT":
                espia.autocommit.append(id(conn))
            return await original_opciones(conn, **opt)

        async def invalidar(conn: AsyncConnection, exception: BaseException | None = None) -> None:
            espia.invalidadas.append(id(conn))
            await original_invalidar(conn, exception)

        monkeypatch.setattr(AsyncConnection, "execution_options", opciones)
        monkeypatch.setattr(AsyncConnection, "invalidate", invalidar)
        return self

    def autocommit_invalidadas(self) -> set[int]:
        """Conexiones que fueron `AUTOCOMMIT` y luego se invalidaron (la del candado)."""
        return set(self.autocommit) & set(self.invalidadas)


# Bloque B4: lista y detalle -------------------------------------------------------------------

AUDIT: Final = "/api/v1/audit"
CAMPOS_ROW: Final = frozenset(
    {
        "seq",
        "at",
        "user_id",
        "user_email",
        "user_name",
        "action",
        "table_name",
        "record_id",
        "subject_member_id",
    }
)
CAMPOS_DETAIL: Final = CAMPOS_ROW | {"before", "after", "prev_hash", "hash", "changes"}
CAMPOS_CHANGE: Final = frozenset({"field", "kind", "before", "after", "encrypted"})
ANA_EMAIL: Final = "ana.perez@ejemplo.local"
ANA_NOMBRE: Final = "ana.perez"
JUAN_EMAIL: Final = "juan.rios@ejemplo.local"
JUAN_NOMBRE: Final = "juan.rios"
TELEFONO_NUEVO: Final = "+57 301 555 0101"
CORREO_NUEVO: Final = "lucia.nueva@correo.co"
IP_REVELAR: Final = "198.51.100.40"
PLAN_NOMBRE: Final = "Mensual Auditoría"
PRECIO: Final = 120_000
MOTIVO_ANULACION: Final = "Pago duplicado de prueba"


def ruta_entrada(seq: int | str) -> str:
    return f"{AUDIT}/{seq}"


class ConId(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def role(self) -> str: ...


@dataclass(frozen=True)
class Actividad:
    plan_id: UUID
    member_id: UUID
    membership_id: UUID
    payment_id: UUID


async def leer_entrada(session: AsyncSession, seq: int) -> dict[str, Any] | None:
    fila = (
        (await session.execute(text("SELECT * FROM audit.audit_log WHERE seq = :s"), {"s": seq}))
        .mappings()
        .first()
    )
    return None if fila is None else dict(fila)


async def filas_de(session: AsyncSession, **filtros: object) -> list[dict[str, Any]]:
    """Filas crudas de `audit.audit_log` con igualdad en cada filtro, en orden de `seq`."""
    condiciones = " AND ".join(f"{campo} = :{campo}" for campo in filtros) or "true"
    consulta = text(f"SELECT * FROM audit.audit_log WHERE {condiciones} ORDER BY seq")  # noqa: S608
    return [dict(f) for f in (await session.execute(consulta, filtros)).mappings().all()]


async def sembrar_actividad(session: AsyncSession, *, ana: ConId, juan: ConId) -> Actividad:
    """La actividad de dos personas por los services reales (ver el docstring del módulo)."""
    session.expunge_all()
    with actor_scope(ana.id):
        plan = await plans_service.create(
            session,
            PlanCreate(name=PLAN_NOMBRE, price_cop=PRECIO, kind="days", duration_days=30),
        )
        socia = await members_service.create(session, entrada())
        await session.commit()
    session.expunge_all()
    with actor_scope(juan.id):
        await members_service.update(
            session,
            socia.id,
            MemberPatch(phone=TELEFONO_NUEVO, email=CORREO_NUEVO),
            role=juan.role,  # type: ignore[arg-type]
        )
        await session.commit()
    session.expunge_all()
    with actor_scope(juan.id):
        await members_service.reveal(session, socia.id, "phone", ip=IP_REVELAR)
        await session.commit()
    session.expunge_all()
    with actor_scope(ana.id):
        venta = await memberships_service.sell(
            session,
            member_id=socia.id,
            plan_id=plan.id,
            role=ana.role,  # type: ignore[arg-type]
        )
        await session.commit()
    session.expunge_all()
    with actor_scope(juan.id):
        pago = await payments_service.register(
            session,
            membership_id=venta.id,
            amount_cop=PRECIO,
            method="cash",
            role=juan.role,  # type: ignore[arg-type]
        )
        await session.commit()
    session.expunge_all()
    with actor_scope(ana.id):
        await payments_service.void(session, payment_id=pago.id, reason=MOTIVO_ANULACION)
        await session.commit()
    session.expunge_all()
    return Actividad(plan.id, socia.id, venta.id, pago.id)
