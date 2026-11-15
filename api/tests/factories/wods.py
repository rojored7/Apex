"""Fábricas de WODs para pruebas con base real (S8-A3). Pasan por el service (audita y copia)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.wods import service
from app.modules.wods.schemas import (
    BenchmarkCreate,
    BenchmarkOut,
    CatalogMovementOut,
    MovementCreate,
    WodCreate,
    WodOut,
)


async def make_movement(
    session: AsyncSession, actor: UUID, name: str = "Thruster", unit: str = "kg", **extra: Any
) -> CatalogMovementOut:
    datos = {"name": name, "category": "weightlifting", "unit": unit, **extra}
    with actor_scope(actor):
        salida = await service.create_movement(session, MovementCreate.model_validate(datos), actor)
        await session.commit()
    return salida


async def make_benchmark(
    session: AsyncSession, actor: UUID, name: str = "Fran", score_type: str = "time"
) -> BenchmarkOut:
    datos = {"name": name, "description": "21-15-9", "score_type": score_type}
    with actor_scope(actor):
        salida = await service.create_benchmark(
            session, BenchmarkCreate.model_validate(datos), actor
        )
        await session.commit()
    return salida


def cuerpo_wod(movement_ids: list[UUID], **cambios: Any) -> dict[str, Any]:
    """Cuerpo de `POST /wods` con un movimiento principal por cada id (posiciones 1..n)."""
    movimientos = [
        {"movement_id": str(mid), "position": i, "reps": "21-15-9", "is_primary": i == 1}
        for i, mid in enumerate(movement_ids, start=1)
    ]
    valores: dict[str, Any] = {
        "date": date(2026, 10, 22).isoformat(),
        "title": "Fran",
        "score_type": "time",
        "time_cap_s": 600,
        "movements": movimientos,
    }
    valores.update(cambios)
    return valores


async def make_wod(
    session: AsyncSession, actor: UUID, movement_ids: list[UUID], **cambios: Any
) -> WodOut:
    with actor_scope(actor):
        salida = await service.create_wod(
            session, WodCreate.model_validate(cuerpo_wod(movement_ids, **cambios)), actor
        )
        await session.commit()
    return salida
