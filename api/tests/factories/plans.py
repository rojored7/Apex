"""Fábrica de `plans.plans` (plan del Sprint 2, sección 2, bloque B9; US-078, US-079).

- `make_plan(session, **cambios)`: inserta un plan "Mensual" de $ 120.000 y 30 días (`days`,
  activo) con los `cambios` que se pidan, bajo `actor_scope(SYSTEM_USER_ID)`; hace `flush` y
  confirma el savepoint. La tabla no tiene columnas cifradas: no necesita el bus.
- `make_plans(session, n, **cambios)`: `n` planes con nombres únicos (`Plan 000`, `Plan 001`...).
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.plans.models import Plan

NOMBRE: Final = "Mensual"
PRECIO: Final = 120_000
DIAS: Final = 30


async def make_plan(session: AsyncSession, **cambios: Any) -> Plan:
    """Inserta un `Plan` (por defecto "Mensual", 120.000, 30 días) bajo `SYSTEM_USER_ID`."""
    valores: dict[str, Any] = {
        "name": NOMBRE,
        "price_cop": PRECIO,
        "kind": "days",
        "duration_days": DIAS,
        "class_count": None,
        "is_active": True,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    plan = Plan(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(plan)
        await session.flush()
        await session.commit()
    return plan


async def make_plans(session: AsyncSession, n: int, **cambios: Any) -> list[Plan]:
    """`n` planes con nombres únicos y ordenables (`Plan 000`, `Plan 001`, ...)."""
    return [await make_plan(session, name=f"Plan {i:03d}", **cambios) for i in range(n)]
