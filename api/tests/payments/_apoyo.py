"""Ayudas de las pruebas de pagos (plan del Sprint 3, sección 2, bloque B3).

- `PAYMENTS` y `METODOS`: rutas del api (`GET /payments/methods`, B3).
- `cuerpo_pago(**cambios)` (un pago de 60.000 en efectivo más lo que se pida) y
  `cuerpo_anulacion(reason)` (B5).
- `CAMPOS_PAYMENT` (claves exactas de `PaymentOut`) y `CAMPOS_METODO` (de `PaymentMethodOut`).
  `CAMPOS_ROW` y `CAMPOS_DETAIL` llegan con las listas y el detalle (B8), que los fijan.
- `registrar(session, actor, **datos)`: `service.register` bajo `actor_scope(actor)` y commit (una
  petición, una transacción; con la `session` de savepoint libera el savepoint).
- `anular(session, actor, **datos)` (S3-B5): `service.void` bajo `actor_scope(actor)` y commit.
- Lecturas con SQL crudo: `leer_pago`, `pagos_de` (orden de `created_at`, `id`),
  `leer_auditoria_de_pagos` y `updates_de(session, table_name, record_id)` (S3-B5: las filas
  `update` de auditoría de un registro con `user_id`, `subject_member_id`, `before` y `after`).
- `DE_ANULACION`: las cuatro columnas de anulación (S3-B5).
- `GateDoble` y `gate_registrado(gate)`: el doble del puerto `MembershipGate` (D1, S3-D74). Toma
  `SELECT ... FOR UPDATE` de la fila REAL de `memberships.memberships` (el mismo candado que el gate
  real de B4: serializa dos pagos de una membresía) y arma `MembershipPayability` con su socio, su
  estado y su precio pactado; `forzados[id]` reemplaza la respuesta de un id. `llamadas` registra
  cada id pedido. `gate_registrado` lo registra con `set_membership_gate` y al salir restaura el
  gate que hubiera (en B3, ninguno).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.payments import service
from app.modules.payments.schemas import PaymentOut
from app.modules.payments.service import MembershipPayability

PAYMENTS = "/api/v1/payments"
METODOS = f"{PAYMENTS}/methods"

CAMPOS_PAYMENT = frozenset(
    {
        "id",
        "membership_id",
        "member_id",
        "amount_cop",
        "method",
        "reference",
        "paid_at",
        "registered_by",
        "voided",
        "void_reason",
        "voided_by",
        "voided_at",
        "created_at",
    }
)
CAMPOS_METODO = frozenset({"code", "label", "hint"})
DE_ANULACION = frozenset({"voided", "void_reason", "voided_by", "voided_at"})


def cuerpo_pago(**cambios: Any) -> dict[str, Any]:
    """Cuerpo de un pago: 60.000 en efectivo más lo que se pida."""
    return {"amount_cop": 60_000, "method": "cash", **cambios}


def cuerpo_anulacion(reason: str) -> dict[str, Any]:
    """Cuerpo de `POST /payments/{payment_id}/void` (B5)."""
    return {"reason": reason}


async def registrar(session: AsyncSession, actor: UUID, **datos: Any) -> PaymentOut:
    """`service.register` bajo `actor_scope(actor)` y commit (rol `coach` si no se pide otro)."""
    datos.setdefault("role", "coach")
    with actor_scope(actor):
        salida = await service.register(session, **datos)
        await session.commit()
    return salida


async def anular(session: AsyncSession, actor: UUID, **datos: Any) -> PaymentOut:
    """`service.void` bajo `actor_scope(actor)` y commit (una petición, una transacción)."""
    with actor_scope(actor):
        salida = await service.void(session, **datos)
        await session.commit()
    return salida


_UPDATES = text(
    "SELECT user_id, subject_member_id, before, after FROM audit.audit_log "
    "WHERE table_name = :t AND record_id = :r AND action = 'update' ORDER BY seq"
)


async def updates_de(
    session: AsyncSession, table_name: str, record_id: UUID
) -> list[dict[str, Any]]:
    """Filas `update` de `audit.audit_log` del registro, en orden de `seq`."""
    filas = await session.execute(_UPDATES, {"t": table_name, "r": record_id})
    return [dict(f) for f in filas.mappings().all()]


_COLUMNAS = (
    "id, membership_id, member_id, amount_cop, method, reference, paid_at, registered_by, "
    "voided, void_reason, voided_by, voided_at, created_at, created_by"
)
_LEER_PAGO = text(f"SELECT {_COLUMNAS} FROM payments.payments WHERE id = :id")  # noqa: S608
_DE_LA_MEMBRESIA = text(
    f"SELECT {_COLUMNAS} FROM payments.payments WHERE membership_id = :m "  # noqa: S608
    "ORDER BY created_at, id"
)


async def leer_pago(session: AsyncSession, payment_id: UUID) -> dict[str, Any] | None:
    fila = (await session.execute(_LEER_PAGO, {"id": payment_id})).mappings().first()
    return dict(fila) if fila is not None else None


async def pagos_de(session: AsyncSession, membership_id: UUID) -> list[dict[str, Any]]:
    filas = (await session.execute(_DE_LA_MEMBRESIA, {"m": membership_id})).mappings().all()
    return [dict(f) for f in filas]


async def leer_auditoria_de_pagos(
    session: AsyncSession, record_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Filas de `audit.audit_log` de `payments.payments` (y del registro, si se da), por `seq`."""
    sql = (
        "SELECT action, record_id, subject_member_id, user_id, after "
        "FROM audit.audit_log WHERE table_name = 'payments.payments'"
    )
    parametros: dict[str, Any] = {}
    if record_id is not None:
        sql += " AND record_id = :r"
        parametros["r"] = record_id
    filas = (await session.execute(text(sql + " ORDER BY seq"), parametros)).mappings().all()
    return [dict(f) for f in filas]


_FILA_BLOQUEADA = text(
    "SELECT member_id, status, agreed_price_cop FROM memberships.memberships "
    "WHERE id = :id FOR UPDATE"
)


@dataclass
class GateDoble:
    """Doble del puerto `MembershipGate` sobre filas reales (ver el docstring del módulo)."""

    forzados: dict[UUID, MembershipPayability] = field(default_factory=dict)
    llamadas: list[UUID] = field(default_factory=list)

    async def __call__(self, session: AsyncSession, membership_id: UUID) -> MembershipPayability:
        self.llamadas.append(membership_id)
        fila = (await session.execute(_FILA_BLOQUEADA, {"id": membership_id})).first()
        if membership_id in self.forzados:
            return self.forzados[membership_id]
        if fila is None:
            return MembershipPayability(
                exists=False, cancelled=False, member_id=None, agreed_price_cop=None
            )
        return MembershipPayability(
            exists=True,
            cancelled=fila.status == "cancelled",
            member_id=fila.member_id,
            agreed_price_cop=fila.agreed_price_cop,
        )


@contextmanager
def gate_registrado(gate: GateDoble) -> Iterator[GateDoble]:
    """Registra `gate` como `MembershipGate` y al salir restaura el anterior."""
    anterior = service.membership_gate()
    service.set_membership_gate(gate)
    try:
        yield gate
    finally:
        service.set_membership_gate(anterior)
