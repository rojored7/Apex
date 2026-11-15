"""Fábrica de `classes.class_slots` (S7-A2, US-155).

- `make_session(session, **cambios)`: inserta una sesión extra (ver su docstring).
- `make_slot(session, **cambios)`: inserta una franja activa (lunes y miércoles 06:00, 60 min,
  cupo 15, sin coach) con los `cambios` que se pidan, bajo `actor_scope(SYSTEM_USER_ID)`; hace
  `flush` y confirma el savepoint. No pasa por el service: no comprueba choques ni coach.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import BOGOTA
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.classes.models import ClassSession, ClassSlot
from app.modules.classes.schemas import CheckinMembership


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


async def make_session(session: AsyncSession, **cambios: Any) -> ClassSession:
    """Inserta una `ClassSession` extra (`slot_id` nulo) con los `cambios` que se pidan.

    Por omisión: mañana jueves 22 de octubre de 2026 a las 06:00 de Bogotá (11:00Z), 60 minutos,
    cupo 15, sin coach. `session_date` sale de `starts_at` en Bogotá si no se pasa. Bajo
    `actor_scope(SYSTEM_USER_ID)`; hace `flush` y confirma el savepoint."""
    valores: dict[str, Any] = {
        "slot_id": None,
        "starts_at": datetime(2026, 10, 22, 11, 0, tzinfo=UTC),
        "duration_min": 60,
        "capacity": 15,
        "coach_id": None,
        "name": None,
        "status": "scheduled",
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    valores.setdefault("session_date", valores["starts_at"].astimezone(BOGOTA).date())
    sesion = ClassSession(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(sesion)
        await session.flush()
        await session.commit()
    return sesion


class FakeMembershipPort:
    """Doble del puerto de membresías de `classes` (S7-D6): devuelve el estado que se le pida y
    anota las llamadas. `status="none"` no trae `membership_id` (sin membresía vigente)."""

    def __init__(self, status: str = "active", *, with_membership: bool = True) -> None:
        self.status = status
        self._with_membership = with_membership
        self._membership_id = uuid4()
        self.views: list[tuple[UUID, date]] = []
        self.locked: list[UUID] = []

    @property
    def membership_id(self) -> UUID | None:
        """Sin membresía con estado `none` (el par de `ck_attendance_membership_pair`, `0029`):
        la prueba puede cambiar `.status` después de crear el doble."""
        return self._membership_id if self._with_membership and self.status != "none" else None

    async def checkin_view(
        self, session: AsyncSession, member_id: UUID, *, on_date: date
    ) -> CheckinMembership:
        self.views.append((member_id, on_date))
        return CheckinMembership(
            membership_id=self.membership_id,
            status=self.status,
            plan_name="Plan de prueba" if self.membership_id else None,
            end_date=None,
            classes_remaining=None,
        )

    async def lock(self, session: AsyncSession, membership_id: UUID) -> None:
        self.locked.append(membership_id)
