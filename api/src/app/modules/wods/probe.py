"""Puerto `ResultsProbe` (S8-A3, S8-D4, S8-D7). Privado del módulo; `service.py` lo reexporta.

`wods` necesita saber cuántos resultados tiene un WOD (`result_count` de la lista y el detalle, y
los campos que se bloquean) sin importar `results` (sentido minoritario, regla de módulos 2 bis).
`results` registra el puerto real con `set_results_probe` al importarse (B1). Sin puerto, lo que
depende de resultados FALLA CERRADO (`ResultsProbeNotRegistered`).

Desde B1 no hay puerto provisional: `results/service.py` registra el real y el resto falla cerrado.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wods.exceptions import RecordsProbeNotRegistered, ResultsProbeNotRegistered


class ResultsProbe(Protocol):
    async def result_counts(
        self, session: AsyncSession, wod_ids: Sequence[UUID]
    ) -> dict[UUID, int]:
        """Resultados vigentes de cada WOD (los ids sin resultados pueden faltar)."""
        ...

    async def referenced_scaled_movements(
        self, session: AsyncSession, wod_id: UUID
    ) -> frozenset[UUID]:
        """Movimientos que algún resultado VIGENTE del WOD cita en `scaled_movement_ids` (L-9)."""
        ...


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


class RecordsProbe(Protocol):
    """Sentido minoritario `wods -> athletes` (S9-D9): ¿hay récords vivos de este elemento?"""

    async def movement_has_records(self, session: AsyncSession, movement_id: UUID) -> bool:
        """Hay un récord NO invalidado del movimiento."""
        ...

    async def benchmark_has_records(self, session: AsyncSession, benchmark_id: UUID) -> bool:
        """Hay un récord NO invalidado del benchmark."""
        ...


_records_probe: RecordsProbe | None = None


def set_records_probe(probe: RecordsProbe | None) -> None:
    """Registra (o quita, con `None`) el puerto. Lo llama `athletes` al importarse."""
    global _records_probe
    _records_probe = probe


def current_records_probe() -> RecordsProbe | None:
    return _records_probe


def records_probe() -> RecordsProbe:
    """El puerto registrado; sin él, `RecordsProbeNotRegistered` (falla cerrado)."""
    if _records_probe is None:
        raise RecordsProbeNotRegistered("nadie registró el puerto RecordsProbe")
    return _records_probe
