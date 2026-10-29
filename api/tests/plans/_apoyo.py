"""Ayudas de las pruebas de planes (S2-B9).

- `cuerpo(**cambios)`: cuerpo JSON de `POST /plans` ("Mensual", $ 120.000, 30 días, `days`).
- `tiquetera(**cambios)`: cuerpo de "Tiquetera 12" (12 clases, 60 días, $ 150.000).
- `entrada(**cambios)`: el cuerpo validado como `PlanCreate`.
- `crear(session, actor, data)`: `service.create` bajo `actor_scope(actor)` y commit (una
  petición, una transacción).
- `fila_plan` y `cuantos_planes`: lecturas con SQL crudo de `plans.plans`.
- `CAMPOS_PLAN`: las claves exactas de `PlanOut` (desde S4A-B7 con `active_members_count`).
- S4A-B7: `ruta_plan(plan_id, accion=None)` (`/plans/{id}`, `/activate` o `/deactivate`),
  `cuerpo_patch(**cambios)` (cuerpo JSON del `PATCH`: solo lo que se pida, así un campo ausente no
  es un cambio), `parche(**cambios)` (validado como `PlanPatch`) y `en_unidad(session, actor,
  coro_factory)` (llama al service bajo `actor_scope(actor)` y confirma: una petición, una
  transacción).
- S4A-B7: `HOY` (el "hoy" de la fixture `reloj`) y `con_membresias(session, plan, estados)`: un
  socio nuevo (`make_members`, necesita el bus) por cada estado EFECTIVO pedido (`active`,
  `expiring`, `pending_payment`, `frozen`, `expired`, `cancelled`), con su membresía del plan
  preparada por las fábricas (sin `sell`). Devuelve las membresías en el orden pedido.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import date, timedelta
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.memberships.models import Membership
from app.modules.plans import service
from app.modules.plans.models import Plan
from app.modules.plans.schemas import PlanCreate, PlanOut, PlanPatch
from tests.factories.members import make_members
from tests.factories.memberships import make_freeze, make_membership

PLANS = "/api/v1/plans"

CAMPOS_PLAN = frozenset(
    {
        "id",
        "name",
        "price_cop",
        "kind",
        "duration_days",
        "class_count",
        "is_active",
        "created_at",
        "updated_at",
        "active_members_count",
    }
)


def cuerpo(**cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "name": "Mensual",
        "price_cop": 120_000,
        "kind": "days",
        "duration_days": 30,
    }
    valores.update(cambios)
    return valores


def tiquetera(**cambios: Any) -> dict[str, Any]:
    """Cuerpo de "Tiquetera 12": 12 clases en 60 días por $ 150.000."""
    valores: dict[str, Any] = {
        "name": "Tiquetera 12",
        "price_cop": 150_000,
        "kind": "classes",
        "duration_days": 60,
        "class_count": 12,
    }
    valores.update(cambios)
    return valores


def entrada(**cambios: Any) -> PlanCreate:
    return PlanCreate.model_validate(cuerpo(**cambios))


async def crear(session: AsyncSession, actor: UUID, data: PlanCreate) -> PlanOut:
    with actor_scope(actor):
        salida = await service.create(session, data)
        await session.commit()
    return salida


async def fila_plan(session: AsyncSession, plan_id: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM plans.plans WHERE id = :id")
    return dict((await session.execute(consulta, {"id": plan_id})).mappings().one())


async def cuantos_planes(session: AsyncSession, *, nombre: str | None = None) -> int:
    """Planes en la tabla (vivos y dados de baja); con `nombre`, los de ese nombre sin
    distinguir mayúsculas ni espacios de los extremos."""
    if nombre is None:
        return int(await session.scalar(text("SELECT count(*) FROM plans.plans")) or 0)
    consulta = text("SELECT count(*) FROM plans.plans WHERE lower(btrim(name)) = lower(btrim(:n))")
    return int(await session.scalar(consulta, {"n": nombre}) or 0)


# S4A-B7 ---------------------------------------------------------------------------------------


def ruta_plan(plan_id: UUID | str, accion: str | None = None) -> str:
    """`/api/v1/plans/{plan_id}` o, con `accion`, `/api/v1/plans/{plan_id}/{accion}`."""
    return f"{PLANS}/{plan_id}" if accion is None else f"{PLANS}/{plan_id}/{accion}"


def cuerpo_patch(**cambios: Any) -> dict[str, Any]:
    """Cuerpo del `PATCH`: exactamente los campos pedidos (un `None` viaja como `null`)."""
    return dict(cambios)


def parche(**cambios: Any) -> PlanPatch:
    return PlanPatch.model_validate(cuerpo_patch(**cambios))


async def en_unidad[T](
    session: AsyncSession, actor: UUID, operacion: Callable[[], Awaitable[T]]
) -> T:
    """`operacion()` bajo `actor_scope(actor)` y commit (con la `session` de savepoint libera el
    savepoint, como `crear`)."""
    with actor_scope(actor):
        salida = await operacion()
        await session.commit()
    return salida


HOY: Final = date(2026, 10, 21)
"""El "hoy" de Bogotá de la fixture `reloj` (`T0`)."""

ESTADOS_ACTIVOS: Final = frozenset({"active", "expiring", "pending_payment", "frozen"})
"""Los que cuentan como activos (N-22, S4A-D24): todo menos `cancelled` y `expired`."""


async def _membresia(session: AsyncSession, socio: Any, plan: Plan, estado: str) -> Membership:
    dias = plan.duration_days
    if estado == "active":
        return await make_membership(session, socio, plan, status="active", start=HOY)
    if estado == "expiring":  # le quedan 4 días
        inicio = HOY - timedelta(days=dias - 4)
        return await make_membership(session, socio, plan, status="active", start=inicio)
    if estado == "pending_payment":
        return await make_membership(session, socio, plan, status="pending_payment", start=HOY)
    if estado == "frozen":
        inicio = HOY - timedelta(days=5)
        membresia = await make_membership(session, socio, plan, status="active", start=inicio)
        await make_freeze(session, membresia, HOY - timedelta(days=1), HOY + timedelta(days=2))
        return membresia
    if estado == "expired":  # terminó hace 10 días
        inicio = HOY - timedelta(days=dias + 10)
        return await make_membership(session, socio, plan, status="active", start=inicio)
    if estado == "cancelled":
        return await make_membership(session, socio, plan, status="cancelled", start=HOY)
    raise ValueError(f"estado desconocido: {estado}")


async def con_membresias(
    session: AsyncSession, plan: Plan, estados: Sequence[str]
) -> list[Membership]:
    """Una membresía del plan por cada estado efectivo pedido, cada una de un socio nuevo."""
    socios = await make_members(session, len(estados))
    return [
        await _membresia(session, socio, plan, estado)
        for socio, estado in zip(socios, estados, strict=True)
    ]
