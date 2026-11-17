"""Eventos de `athletes` (S9-D12). Sin valores ni texto libre (S3-D70). A1 no emitía ninguno.

`PersonalRecordSet` (S9-B1): un récord nuevo quedó VIGENTE (US-180 CA7). Lleva ids, el tipo, el
origen y la fecha civil; nunca el valor ni el nombre (quien lo consuma, EP-25 US-195, lee el récord
por id). Sin suscriptores en v0.6. Se exporta desde `athletes/service.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalRecordSet(DomainEvent):
    record_id: UUID
    member_id: UUID
    kind: Literal["rm", "benchmark"]
    movement_id: UUID | None
    benchmark_id: UUID | None
    source: Literal["manual", "derived"]
    achieved_on: date
