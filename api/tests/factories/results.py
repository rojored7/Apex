"""Fábricas de resultados para pruebas con base real (S8-B1). Pasan por el service (audita)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.results import service
from app.modules.results.schemas import ResultIn, ResultOut


async def make_result(
    session: AsyncSession, actor: UUID, wod_id: UUID, member_id: UUID, **cambios: Any
) -> ResultOut:
    """Registra un resultado `rx` de 300 s (WOD de tiempo, sin clase) y confirma el savepoint."""
    datos: dict[str, Any] = {
        "wod_id": wod_id,
        "member_id": member_id,
        "level": "rx",
        "seconds": 300,
    }
    datos.update(cambios)
    with actor_scope(actor):
        salida = await service.record_result(
            session, ResultIn.model_validate(datos), by=actor, source="desk"
        )
        await session.commit()
    return salida
