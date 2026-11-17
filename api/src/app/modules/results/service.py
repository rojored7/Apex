"""Fachada del service de `results` (S8-B1). Lo único que importan los demás módulos.

- `record.py` (S8-B1, US-169, US-170): `record_result` (registra y corrige) y el puerto de
  `classes` (`session_has_current_results`).
- `events.py`: `WodResultRecorded` y `WodResultValidated`.
Al importarse registra dos puertos (sentido minoritario, regla 2 bis): `wods.set_results_probe`
(cuántos resultados vigentes tiene un WOD) y `classes.set_results_port` (si una sesión tiene
resultados vigentes). Lo importan `create_app`, el CLI y el worker con `load_module_services()`.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.classes import service as classes_service
from app.modules.results.attendance import session_attendance
from app.modules.results.events import (
    WodResultRecorded,
    WodResultSuperseded,
    WodResultValidated,
    WodResultVoided,
)
from app.modules.results.leaderboard import score_key
from app.modules.results.models import WodResult
from app.modules.results.reads import (
    MEMBER_MARKS_MAX,
    get_mark,
    leaderboard,
    member_marks,
    member_results,
    public_leaderboard,
    result_sources,
    wod_results,
)
from app.modules.results.record import (
    member_has_current_result_in_session,
    record_result,
    session_has_current_results,
    sessions_with_current_results,
)
from app.modules.results.rules import validate_score
from app.modules.results.schemas import ResultMark
from app.modules.results.void import void_result
from app.modules.wods import service as wods_service


class _Probe:
    """`wods.ResultsProbe`: resultados vigentes por WOD, en UNA consulta."""

    async def result_counts(
        self, session: AsyncSession, wod_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        if not wod_ids:
            return {}
        filas = await session.execute(
            select(WodResult.wod_id, func.count())
            .where(WodResult.wod_id.in_(list(wod_ids)), WodResult.is_current)
            .group_by(WodResult.wod_id)
        )
        return {wod_id: int(total) for wod_id, total in filas.all()}

    async def referenced_scaled_movements(
        self, session: AsyncSession, wod_id: UUID
    ) -> frozenset[UUID]:
        filas = await session.scalars(
            select(func.unnest(WodResult.scaled_movement_ids))
            .where(WodResult.wod_id == wod_id, WodResult.is_current)
            .distinct()
        )
        return frozenset(filas.all())


class _SessionPort:
    """`classes.ResultsPort`."""

    async def session_has_current_results(self, session: AsyncSession, session_id: UUID) -> bool:
        return await session_has_current_results(session, session_id)

    async def sessions_with_current_results(
        self, session: AsyncSession, session_ids: Sequence[UUID]
    ) -> set[UUID]:
        return await sessions_with_current_results(session, session_ids)

    async def member_has_current_result_in_session(
        self, session: AsyncSession, session_id: UUID, member_id: UUID
    ) -> bool:
        return await member_has_current_result_in_session(session, session_id, member_id)


results_probe = _Probe()
wods_service.set_results_probe(results_probe)
classes_service.set_results_port(_SessionPort())

# Nombres públicos de las dos listas de lectura (S8-B4).
list_wod_results = wod_results
list_member_results = member_results

__all__ = [
    "MEMBER_MARKS_MAX",
    "ResultMark",
    "WodResultRecorded",
    "WodResultSuperseded",
    "WodResultValidated",
    "WodResultVoided",
    "get_mark",
    "leaderboard",
    "list_member_results",
    "list_wod_results",
    "member_marks",
    "public_leaderboard",
    "record_result",
    "result_sources",
    "results_probe",
    "score_key",
    "session_attendance",
    "session_has_current_results",
    "sessions_with_current_results",
    "validate_score",
    "void_result",
]
