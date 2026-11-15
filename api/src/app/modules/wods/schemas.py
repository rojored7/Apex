"""Contrato de movimientos (S8-A1, US-165; S8-D5).

- `MovementCreate` (`extra="forbid"`): `name` (1 a 60, `SafeText`), `category` y `unit` (enums).
- `MovementPatch` (`extra="forbid"`): todo opcional; ningún campo admite `null` (el service lo
  rechaza con 422 y `field`).
- `CatalogMovementOut`: la respuesta, con `wod_count` (WODs que lo usan; 0 hasta A3).
- `MovementListQuery`: filtros de la lista (`category`, `active`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.core.validators import SafeText
from app.modules.wods.rules import NAME_MAX_LENGTH

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
