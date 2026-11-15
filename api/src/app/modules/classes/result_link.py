"""Lo que `results` y `classes` se piden entre sí (S8-B1, S8-D36, M-6; revisión de A4, M-2 y M-3).
Privado del módulo: lo reexporta `service.py`.

- `session_for_result(session, session_id, member_id) -> ResultSession`: la sesión con `FOR SHARE`
  (el mismo candado de fila que toman el check-in, las cancelaciones y `PATCH /class-sessions`, que
  piden `FOR UPDATE`: esperan a que el resultado confirme). Exige `status = scheduled` (409
  `session_cancelled`, AUNQUE tenga asistencias vivas) y asistencia viva del socio (422
  `field = "session_id"`). Devuelve el WOD EFECTIVO: el asignado o, sin asignar, el del día; con
  `inherited = True` quien llama debe recomprobar, tras el `FOR SHARE` del WOD, que su fecha sigue
  siendo la de la sesión (M-3).
- Puerto `ResultsPort` (`set_results_port`, `results_port`): `results` lo registra al importarse;
  `assign_wod` lo pide para negar el cambio del WOD efectivo de una sesión con resultados vigentes
  (M-2). Sin puerto falla cerrado (`ResultsPortNotRegistered`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes.attendance import alive_attendance_id
from app.modules.classes.exceptions import (
    ClassValidationError,
    ResultsPortNotRegistered,
    SessionCancelledError,
    SessionNotFound,
)
from app.modules.classes.models import ClassSession
from app.modules.wods import service as wods_service


@dataclass(frozen=True, slots=True)
class ResultSession:
    """La sesión que respalda un resultado: su fecha y su WOD efectivo."""

    session_id: UUID
    session_date: date
    wod_id: UUID | None
    inherited: bool


async def session_for_result(
    session: AsyncSession, session_id: UUID, member_id: UUID
) -> ResultSession:
    fila = await session.scalar(
        select(ClassSession)
        .where(ClassSession.id == session_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if fila is None:
        raise SessionNotFound()
    if fila.status == "cancelled":
        raise SessionCancelledError()
    if await alive_attendance_id(session, fila.id, member_id) is None:
        raise ClassValidationError(
            message="El socio no tiene asistencia en esa clase.", field="session_id"
        )
    if fila.wod_id is not None:
        return ResultSession(fila.id, fila.session_date, fila.wod_id, inherited=False)
    del_dia = await wods_service.day_wod_ids(session, {fila.session_date})
    return ResultSession(fila.id, fila.session_date, del_dia.get(fila.session_date), inherited=True)


class ResultsPort(Protocol):
    async def session_has_current_results(self, session: AsyncSession, session_id: UUID) -> bool:
        """¿Hay resultados vigentes registrados desde esa sesión?"""
        ...


_port: ResultsPort | None = None


def set_results_port(port: ResultsPort | None) -> None:
    """Registra (o quita, con `None`) el puerto; solo lo llama `results/service.py`."""
    global _port
    _port = port


def results_port() -> ResultsPort:
    if _port is None:
        raise ResultsPortNotRegistered("classes: ResultsPort sin registrar")
    return _port
