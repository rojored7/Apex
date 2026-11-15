"""Apoyo de las pruebas de `results` (S8-B1): WOD, clase y socio presente."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.classes.models import ClassSession
from app.modules.members.models import Member
from app.modules.results import service
from app.modules.results.schemas import ResultIn, ResultOut
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_members
from tests.factories.users import make_user
from tests.factories.wods import make_movement, make_wod

HOY = date(2026, 10, 21)  # `reloj` (T0) = 21 de octubre de 2026, 10:00 de Bogotá
CLASE_HOY = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


@dataclass
class Escena:
    coach: UUID
    socio: Member
    socio_id: UUID
    wod_id: UUID
    movimientos: list[UUID]
    clase: ClassSession | None
    clase_id: UUID | None = None


async def escena(
    session: AsyncSession,
    *,
    score_type: str = "time",
    time_cap_s: int | None = 600,
    fecha: str = "2026-10-21",
    con_clase: bool = True,
    asistencia: bool = True,
) -> Escena:
    coach = await make_user(session, role="coach")
    uno = await make_movement(session, coach.id, name=f"Mov uno {fecha}", unit="kg")
    dos = await make_movement(session, coach.id, name=f"Mov dos {fecha}", unit="reps")
    cambios: dict[str, Any] = {"date": fecha, "score_type": score_type, "time_cap_s": time_cap_s}
    wod = await make_wod(session, coach.id, [uno.id, dos.id], **cambios)
    socio = (await make_members(session, 1))[0]
    clase = None
    if con_clase:
        clase = await make_session(session, starts_at=CLASE_HOY)
        if asistencia:
            await make_attendance(session, clase, socio.id)
    return Escena(
        coach.id, socio, socio.id, wod.id, [uno.id, dos.id], clase, clase.id if clase else None
    )


def cuerpo(e: Escena, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "wod_id": e.wod_id,
        "member_id": e.socio_id,
        "level": "rx",
        "seconds": 300,
    }
    if e.clase_id is not None:
        valores["session_id"] = e.clase_id
    valores.update(cambios)
    return valores


async def registrar(
    session: AsyncSession, e: Escena, *, source: str = "desk", **cambios: Any
) -> ResultOut:
    datos = ResultIn.model_validate(cuerpo(e, **cambios))
    with actor_scope(e.coach):
        return await service.record_result(session, datos, by=e.coach, source=source)
