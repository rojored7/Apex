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

from app.core.validators import SafeText
from app.modules.classes.schemas import SessionOut
from app.modules.wods.schemas import WodOut

ResultLevel = Literal["rx", "rx_plus", "scaled"]
ResultStatus = Literal["validated", "pending", "voided"]
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


class VoidIn(BaseModel):
    """`POST /results/{id}/void` (S8-D46 b): el motivo es obligatorio (1 a 200, `SafeText`: sin
    controles, invisibles ni bidireccionales; revisión de B4, M-1)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: Annotated[SafeText, Field(min_length=1, max_length=200)]


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
    voided_by: UUID | None
    voided_at: datetime | None
    void_reason: str | None
    created_at: datetime
    updated_at: datetime


class AttendanceResultRow(BaseModel):
    """Un asistente vivo de la clase y su resultado vigente en el WOD efectivo (S8-D14).

    Solo nombre y apellido: ningún campo cifrado. `result` prellena la tablet y da el
    `supersedes_id` de una corrección."""

    member_id: UUID
    first_name: str
    last_name: str
    has_result: bool
    result: ResultOut | None


class SessionAttendanceOut(BaseModel):
    """`GET /class-sessions/{session_id}/attendance` (S8-B3, US-169 CA1)."""

    session: SessionOut
    wod: WodOut | None
    items: list[AttendanceResultRow]
    total: int
    limit: int
    offset: int


class LeaderboardRow(BaseModel):
    """Una fila del leaderboard (S8-B4, US-171, S8-D13). Solo nombre y inicial del apellido: ningún
    campo cifrado. La carga va en gramos (`load_g`, S8-D41)."""

    position: int
    result_id: UUID
    member_id: UUID
    first_name: str
    last_initial: str
    level: ResultLevel
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool


class PublicRow(BaseModel):
    """Fila del ranking público de la TV (S8-C2, S8-D34): sin `member_id`, sexo ni notas. Solo lo
    necesita `tv.rules.to_public_board`; `first_name` y `last_name` en claro, nunca cifrados."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int
    first_name: str
    last_name: str
    level: ResultLevel
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool


class WodResultRow(BaseModel):
    """Una fila de `GET /wods/{id}/results` (S8-B4, US-172): socio, marca, quién y cuándo."""

    id: UUID
    member_id: UUID
    first_name: str
    last_name: str
    level: ResultLevel
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    status: ResultStatus
    source: ResultSource
    is_current: bool
    supersedes_id: UUID | None
    session_id: UUID | None
    recorded_by: UUID
    recorded_by_name: str | None
    created_at: datetime


class MemberResultRow(BaseModel):
    """Una fila de `GET /members/{id}/results` (S8-B4, US-173): el WOD copiado y la marca."""

    id: UUID
    wod_id: UUID
    wod_date: date_type
    wod_title: str
    score_type: str
    benchmark_id: UUID | None
    is_benchmark: bool
    level: ResultLevel
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    status: ResultStatus
    source: ResultSource
    session_id: UUID | None
    created_at: datetime
