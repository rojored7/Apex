"""Eventos de `wods` (S8-A3, S8-D7). Sin datos personales ni texto libre (S3-D70).

- `WodPublished(wod_id, wod_date)` (US-166 CA1): un WOD se creó. Se exporta desde `service.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class WodPublished(DomainEvent):
    wod_id: UUID
    wod_date: date
