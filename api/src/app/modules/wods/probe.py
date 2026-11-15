"""Puerto `ResultsProbe` (S8-A3, S8-D4, S8-D7). Privado del módulo; `service.py` lo reexporta.

`wods` necesita saber cuántos resultados tiene un WOD (`result_count` de la lista y el detalle, y
los campos que se bloquean) sin importar `results` (sentido minoritario, regla de módulos 2 bis).
`results` registra el puerto real con `set_results_probe` al importarse (B1). Sin puerto, lo que
depende de resultados FALLA CERRADO (`ResultsProbeNotRegistered`).

Mientras `results` no existe (A3 y A4) `service.py` registra `NoResultsYet`: sin la tabla de
resultados, cero es la verdad. B1 lo reemplaza con el real y lo quita.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods.exceptions import ResultsProbeNotRegistered


class ResultsProbe(Protocol):
    async def result_counts(
        self, session: AsyncSession, wod_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        """Resultados vigentes de cada WOD (los ids sin resultados pueden faltar)."""
        ...


class NoResultsYet:
    """Provisional de A3: la tabla de resultados nace en B1, así que ningún WOD tiene resultados."""

    async def result_counts(
        self, session: AsyncSession, wod_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        return dict.fromkeys(wod_ids, 0)


_probe: ResultsProbe | None = None


def set_results_probe(probe: ResultsProbe | None) -> None:
    """Registra (o quita, con `None`) el puerto. Lo llama `results` al importarse."""
    global _probe
    _probe = probe


def current_results_probe() -> ResultsProbe | None:
    return _probe


def results_probe() -> ResultsProbe:
    """El puerto registrado; sin él, `ResultsProbeNotRegistered` (falla cerrado)."""
    if _probe is None:
        raise ResultsProbeNotRegistered("nadie registró el puerto ResultsProbe")
    return _probe
