"""Ayudas de las pruebas de planes (S2-B9).

- `cuerpo(**cambios)`: cuerpo JSON de `POST /plans` ("Mensual", $ 120.000, 30 días, `days`).
- `tiquetera(**cambios)`: cuerpo de "Tiquetera 12" (12 clases, 60 días, $ 150.000).
- `entrada(**cambios)`: el cuerpo validado como `PlanCreate`.
- `crear(session, actor, data)`: `service.create` bajo `actor_scope(actor)` y commit (una
  petición, una transacción).
- `fila_plan` y `cuantos_planes`: lecturas con SQL crudo de `plans.plans`.
- `CAMPOS_PLAN`: las claves exactas de `PlanOut`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.plans import service
from app.modules.plans.schemas import PlanCreate, PlanOut

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
