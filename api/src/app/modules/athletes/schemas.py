"""Esquemas HTTP de `athletes` (S9-A1, US-178; contrato del blueprint §3, rutas 1 y 2).

`MetricIn` (`extra="forbid"`): enteros estrictos (gramos, centímetros, porcentaje; S9-D3). Los
RANGOS (peso 20000..400000, estatura 50..250, grasa 1..75, notas 1..500) y la fecha (de 2000 a hoy
en Bogotá) los valida `rules.validate_metric` (una sola fuente, también para los servicios que
llaman sin HTTP) y salen como 422 con `field`. `MetricOut` nunca trae un valor: solo las marcas
`has_*` (la lista no descifra).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import SafeText

WeightGrams = Annotated[int, Field(strict=True, description="Gramos, 20000 a 400000.")]
HeightCm = Annotated[int, Field(strict=True, description="Centímetros, 50 a 250.")]
BodyFatPct = Annotated[int, Field(strict=True, description="Porcentaje entero, 1 a 75.")]


class MetricIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_on: date
    weight_g: WeightGrams | None = None
    height_cm: HeightCm | None = None
    body_fat_pct: BodyFatPct | None = None
    notes: SafeText | None = Field(default=None, description="Texto de 1 a 500 caracteres.")


class MetricOut(BaseModel):
    id: UUID
    measured_on: date
    has_weight: bool
    has_height: bool
    has_body_fat: bool
    has_notes: bool
    recorded_by: UUID
    recorded_by_name: str | None
    voided_at: datetime | None
    created_at: datetime


RevealField = Literal["weight_g", "height_cm", "body_fat_pct", "notes"]
"""Los cuatro campos cifrados de una medición: lo único que `reveal` acepta (S9-D15)."""


class MetricRevealIn(BaseModel):
    """`POST .../metrics/{metric_id}/reveal`: UN campo por petición; claves de más dan 422."""

    model_config = ConfigDict(extra="forbid")

    field: RevealField


class MetricRevealOut(BaseModel):
    """El valor en claro de UN campo (`int` para peso en gramos, estatura en cm y grasa en %;
    `str` para las notas; `None` si el campo está vacío). Viaja solo en esta respuesta, con
    `Cache-Control: no-store`; nunca se guarda ni se registra."""

    field: RevealField
    value: int | str | None


# S9-B1 (US-180; contrato del blueprint §3, rutas 4 y 5) --------------------------------------

RecordKind = Literal["rm", "benchmark"]
RecordLevel = Literal["rx", "rx_plus", "scaled"]
Whole = Annotated[int, Field(strict=True)]


class RecordIn(BaseModel):
    """`POST /athletes/{member_id}/records`: un récord manual. `extra="forbid"` (nada de `capped`,
    `source`, `result_id` ni `invalidated_*`). Los RANGOS y las combinaciones de campos por `kind`
    (RM: `movement_id` y `value_g`; benchmark: `benchmark_id` y `level`) los valida el service y
    salen como 422 con `field`."""

    model_config = ConfigDict(extra="forbid")

    kind: RecordKind
    achieved_on: date
    movement_id: UUID | None = None
    value_g: Whole | None = Field(default=None, description="Gramos, 1 a 1000000 (solo `rm`).")
    benchmark_id: UUID | None = None
    level: RecordLevel | None = None
    seconds: Whole | None = None
    rounds: Whole | None = None
    reps: Whole | None = None
    load_g: Whole | None = None


class RecordOut(BaseModel):
    """Un récord con los nombres del catálogo. `is_current`: el mejor no invalidado de su objetivo
    (movimiento o benchmark) del socio; se calcula por página con UNA consulta."""

    id: UUID
    kind: RecordKind
    movement_id: UUID | None
    movement_name: str | None
    benchmark_id: UUID | None
    benchmark_name: str | None
    score_type: str | None
    value_g: int | None
    level: RecordLevel | None
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    achieved_on: date
    source: Literal["manual", "derived"]
    result_id: UUID | None
    result_source: Literal["desk", "kiosk"] | None = None
    wod_id: UUID | None
    is_current: bool
    invalidated_at: datetime | None
    invalidated_reason: Literal["superseded", "voided", "manual_error"] | None
    recorded_by: UUID
    recorded_by_name: str | None
    created_at: datetime
