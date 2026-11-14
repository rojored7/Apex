"""Fábrica de `classes.class_slots` (S7-A2, US-155).

- `make_slot(session, **cambios)`: inserta una franja activa (lunes y miércoles 06:00, 60 min,
  cupo 15, sin coach) con los `cambios` que se pidan, bajo `actor_scope(SYSTEM_USER_ID)`; hace
  `flush` y confirma el savepoint. No pasa por el service: no comprueba choques ni coach.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.classes.models import ClassSlot


async def make_slot(session: AsyncSession, **cambios: Any) -> ClassSlot:
    """Inserta un `ClassSlot` (por defecto lunes y miércoles 06:00, 60 min, cupo 15)."""
    valores: dict[str, Any] = {
        "weekdays": [0, 2],
        "start_time": "06:00",
        "duration_min": 60,
        "capacity": 15,
        "default_coach_id": None,
        "name": None,
        "valid_from": date(2026, 10, 21),
        "is_active": True,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    franja = ClassSlot(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(franja)
        await session.flush()
        await session.commit()
    return franja
