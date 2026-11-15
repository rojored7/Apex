"""Contrato de movimientos (S8-A1, US-165; S8-D5).

- `MovementCreate` (`extra="forbid"`): `name` (1 a 60, `SafeText`), `category` y `unit` (enums).
- `MovementPatch` (`extra="forbid"`): todo opcional; ningún campo admite `null` (el service lo
  rechaza con 422 y `field`).
- `CatalogMovementOut`: la respuesta, con `wod_count` (WODs que lo usan; 0 hasta A3).
- `MovementListQuery`: filtros de la lista (`category`, `active`).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool

from app.core.validators import SafeText, check_multiline_text, check_visible_text
from app.modules.wods.rules import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH

MovementCategory = Literal["weightlifting", "gymnastics", "monostructural", "other"]
MovementUnit = Literal["kg", "reps", "m", "cal", "s"]
MovementName = Annotated[SafeText, Field(min_length=1, max_length=NAME_MAX_LENGTH)]


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: MovementName
    category: MovementCategory
    unit: MovementUnit


class MovementPatch(BaseModel):
    """`PATCH /movements/{id}`: un campo ausente no es un cambio (`model_fields_set`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: MovementName | None = None
    category: MovementCategory | None = None
    unit: MovementUnit | None = None
    is_active: StrictBool | None = None


class CatalogMovementOut(BaseModel):
    id: UUID
    name: str
    category: MovementCategory
    unit: MovementUnit
    is_active: bool
    wod_count: int
    created_at: datetime
    updated_at: datetime


class MovementListQuery(BaseModel):
    """Filtros de la lista; el router los arma desde la query string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: MovementCategory | None = None
    active: bool | None = None


# S8-A2 (US-166, S8-D6): benchmarks -------------------------------------------------------------

BenchmarkScoreType = Literal["time", "rounds_reps", "reps", "load"]


def _check_description(value: str) -> str:
    """Vacía vale (0 a 2.000); si trae algo, `SafeMultilineText` (admite saltos de línea)."""
    return check_multiline_text(value) if value.strip() else ""


BenchmarkDescription = Annotated[
    str, AfterValidator(_check_description), Field(max_length=DESCRIPTION_MAX_LENGTH)
]


class BenchmarkCreate(BaseModel):
    """`POST /benchmarks`: `description` es opcional (vacía por defecto)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: MovementName
    description: BenchmarkDescription = ""
    score_type: BenchmarkScoreType


class BenchmarkPatch(BaseModel):
    """`PATCH /benchmarks/{id}`: un campo ausente no es un cambio; ninguno admite `null`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: MovementName | None = None
    description: BenchmarkDescription | None = None
    score_type: BenchmarkScoreType | None = None


class BenchmarkOut(BaseModel):
    id: UUID
    name: str
    description: str
    score_type: BenchmarkScoreType
    wod_count: int
    created_at: datetime
    updated_at: datetime


class BenchmarkListQuery(BaseModel):
    """Filtro de la lista: por tipo de marca."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score_type: BenchmarkScoreType | None = None


# S8-A3 (US-166, US-167, S8-D7, S8-D8, S8-D41): WODs --------------------------------------------

WodScoreType = Literal["time", "rounds_reps", "reps", "load", "none"]
LoadGrams = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
WodTitle = Annotated[SafeText, Field(min_length=1, max_length=80)]


def _check_short(value: str) -> str:
    """Texto corto de una línea (reps, notas): vacío vale; si trae algo, `SafeText`."""
    return check_visible_text(value) if value.strip() else ""


ShortText40 = Annotated[str, AfterValidator(_check_short), Field(max_length=40)]
ShortText200 = Annotated[str, AfterValidator(_check_short), Field(max_length=200)]


class WodMovementIn(BaseModel):
    """Un movimiento del WOD. `position` de 1 a n (lo comprueba `validate_wod`); las cargas son
    gramos enteros de 0 a 1.000.000 (S8-D41)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    movement_id: UUID
    position: Annotated[int, Field(strict=True)]
    reps: ShortText40 = ""
    load_rx_m_g: LoadGrams | None = None
    load_rx_f_g: LoadGrams | None = None
    notes: ShortText200 = ""
    is_primary: StrictBool = False


class WodCreate(BaseModel):
    """`POST /wods`. `time_cap_s` y `movements` se validan en `validate_wod` (422 con `field`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: date_type
    title: WodTitle
    score_type: WodScoreType
    time_cap_s: Annotated[int, Field(strict=True)] | None = None
    benchmark_id: UUID | None = None
    description: BenchmarkDescription = ""
    movements: list[WodMovementIn]


class WodPatch(BaseModel):
    """`PATCH /wods/{id}`: un campo ausente no es un cambio. `time_cap_s` y `benchmark_id`
    admiten `null` (quitarlos); los demás no."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: date_type | None = None
    title: WodTitle | None = None
    score_type: WodScoreType | None = None
    time_cap_s: Annotated[int, Field(strict=True)] | None = None
    benchmark_id: UUID | None = None
    description: BenchmarkDescription | None = None
    movements: list[WodMovementIn] | None = None


class WodMovementOut(BaseModel):
    id: UUID
    movement_id: UUID
    movement_name: str
    position: int
    reps: str
    load_rx_m_g: int | None
    load_rx_f_g: int | None
    notes: str
    is_primary: bool


class WodOut(BaseModel):
    id: UUID
    date: date_type
    title: str
    score_type: WodScoreType
    time_cap_s: int | None
    benchmark_id: UUID | None
    benchmark_name: str | None
    is_benchmark: bool
    description: str
    movements: list[WodMovementOut]
    result_count: int
    created_at: datetime
    updated_at: datetime


class WodRowOut(BaseModel):
    """Fila de la lista y del calendario: sin la lista de movimientos."""

    id: UUID
    date: date_type
    title: str
    score_type: WodScoreType
    time_cap_s: int | None
    benchmark_id: UUID | None
    benchmark_name: str | None
    is_benchmark: bool
    movement_count: int
    movement_names: list[str]
    result_count: int


class WodListQuery(BaseModel):
    """`week` (AAAA-Www, 7 días sin paginar) o `q`/`benchmark` (paginado); no se combinan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week: str | None = None
    benchmark: bool | None = None
