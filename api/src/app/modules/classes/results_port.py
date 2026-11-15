"""Puerto de resultados de `classes` (S8-B1, S8-B1d; S8-D46). Privado del módulo.

`results` lo registra al importarse (`set_results_port`); `classes` lo consulta para negar lo que
dejaría un resultado vigente sobre un WOD distinto (`assign_wod`), una asistencia muerta
(`remove_attendance`) o una sesión cancelada (`cancel_session`, `cancel_future_sessions`). Sin
puerto falla cerrado (`ResultsPortNotRegistered`). Vive aparte de `result_link.py` para que
`attendance.py` lo importe sin ciclo.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes.exceptions import ResultsPortNotRegistered


class ResultsPort(Protocol):
    async def session_has_current_results(self, session: AsyncSession, session_id: UUID) -> bool:
        """¿Hay resultados vigentes registrados desde esa sesión?"""
        ...

    async def sessions_with_current_results(
        self, session: AsyncSession, session_ids: Sequence[UUID]
    ) -> set[UUID]:
        """De esas sesiones, las que tienen resultados vigentes (una consulta; V7, M-1)."""
        ...

    async def member_has_current_result_in_session(
        self, session: AsyncSession, session_id: UUID, member_id: UUID
    ) -> bool:
        """¿Ese socio tiene un resultado vigente registrado desde esa sesión?"""
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
