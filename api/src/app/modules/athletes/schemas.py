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
