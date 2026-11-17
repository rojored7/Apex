"""Eventos de `results` (S8-B1, S8-D11). Sin datos personales ni texto libre (S3-D70).

- `WodResultRecorded`: un resultado se registró (EP-24 lo usa para los récords personales).
- `WodResultValidated`: un resultado quedó validado (hoy, en la misma transacción que el registro).
Sin suscriptores en v0.5. Se exportan desde `service.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class WodResultRecorded(DomainEvent):
    result_id: UUID
    member_id: UUID
    wod_id: UUID
    level: str
    load_g: int | None
    primary_movement_id: UUID | None


@dataclass(frozen=True, slots=True, kw_only=True)
class WodResultValidated(DomainEvent):
    result_id: UUID
    member_id: UUID
    wod_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class WodResultVoided(DomainEvent):
    """Un admin anuló un resultado (S8-D46 b). Sin el motivo (texto libre, S3-D70)."""

    result_id: UUID
    member_id: UUID
    wod_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class WodResultSuperseded(DomainEvent):
    """Una corrección reemplazó un resultado (S9-D7, S9-B5). Solo ids: se emite tras el `INSERT`
    del nuevo y ANTES de `WodResultRecorded` y `WodResultValidated` (el récord del anterior se
    invalida antes de que el nuevo derive)."""

    old_result_id: UUID
    new_result_id: UUID
    member_id: UUID
    wod_id: UUID
