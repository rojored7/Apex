"""Contrato de resultados (S8-B1, US-169; S8-D11, S8-D41).

`ResultIn` (`extra="forbid"`): las cargas son gramos enteros (0 a 1.000.000). `source`, `status` y
`recorded_by` nunca vienen del cliente.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

ResultLevel = Literal["rx", "rx_plus", "scaled"]
ResultStatus = Literal["validated", "pending"]
ResultSource = Literal["desk", "kiosk"]
Seconds = Annotated[int, Field(strict=True, ge=1, le=86_400)]
Rounds = Annotated[int, Field(strict=True, ge=0, le=1_000)]
Reps = Annotated[int, Field(strict=True, ge=0, le=100_000)]
LoadGrams = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]


class ResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wod_id: UUID
    member_id: UUID
    session_id: UUID | None = None
    level: ResultLevel
    seconds: Seconds | None = None
    rounds: Rounds | None = None
    reps: Reps | None = None
    load_g: LoadGrams | None = None
    capped: StrictBool = False
    scaled_movement_ids: Annotated[list[UUID], Field(max_length=30)] = Field(default_factory=list)
    supersedes_id: UUID | None = None


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wod_id: UUID
    member_id: UUID
    session_id: UUID | None
    wod_date: date_type
    benchmark_id: UUID | None
    level: ResultLevel
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    scaled_movement_ids: list[UUID]
    status: ResultStatus
    recorded_by: UUID
    validated_by: UUID | None
    validated_at: datetime | None
    supersedes_id: UUID | None
    is_current: bool
    source: ResultSource
    created_at: datetime
    updated_at: datetime
