"""Contrato de planes (S2-B9, US-078 y US-079; DECISIÓN 32, S2-D26, S2-D32).

- `PlanCreate` (`extra="forbid"`, `str_strip_whitespace=True`): `name` de 1 a 80 caracteres tras
  recortar, en NFC, sin caracteres de control ni de formato y con algo visible; `price_cop` de
  1 a 1.000.000.000, `duration_days` de 1 a 3.650 y `class_count` de 1 a 1.000 (o nulo).
  Los enteros son `StrictInt`: `120000.5`, `"120000"` y `true` dan 422. La regla
  que cruza `kind` y `class_count` la aplica `service.validate_plan`.
- `PlanOut`: la respuesta de alta, lista y detalle; `price_cop` siempre entero.
- `PlanSnapshot`: dataclass congelada, el contrato que `memberships` importará (nunca el ORM).
- `PlanListQuery`: filtros de la lista (`q` hasta 100 caracteres sin controles, como
  `SearchQuery`; nunca se registra; `active`).
- S4A-B7 (US-080, S4A-D22): `PlanPatch` (`extra="forbid"`: `is_active` y `deleted_at` en el
  cuerpo dan 422), todos opcionales con los topes de `PlanCreate`; `model_fields_set` distingue
  no enviado de `null`. `PlanState`: el plan resultante de `service.merge_plan` (pura).
  S4A-D25: `PlanOut.active_members_count` (membresías con estado efectivo distinto de
  `cancelled` y `expired`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.core.pagination import MAX_SEARCH_LENGTH, SEARCH_PATTERN
from app.core.validators import SafeText

PlanKind = Literal["days", "classes"]

NAME_MAX_LENGTH: Final[int] = 80
PRICE_COP_MIN: Final[int] = 1
PRICE_COP_MAX: Final[int] = 1_000_000_000
DURATION_DAYS_MIN: Final[int] = 1
DURATION_DAYS_MAX: Final[int] = 3_650
CLASS_COUNT_MIN: Final[int] = 1
CLASS_COUNT_MAX: Final[int] = 1_000


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # `SafeText` (revisión S2-B9 M1, unificado en la revisión del Sprint 2): NFC (así
    # "Promoción" compuesta y descompuesta chocan en `uq_plans_name_alive`), sin `Cc` ni `Cf`
    # (un NUL daba 500 y un U+200B pasaba el CHECK `btrim(name) <> ''`) y algo visible.
    name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    price_cop: StrictInt = Field(ge=PRICE_COP_MIN, le=PRICE_COP_MAX)
    kind: PlanKind
    duration_days: StrictInt = Field(ge=DURATION_DAYS_MIN, le=DURATION_DAYS_MAX)
    class_count: StrictInt | None = Field(default=None, ge=CLASS_COUNT_MIN, le=CLASS_COUNT_MAX)


class PlanPatch(BaseModel):
    """`PATCH /plans/{plan_id}` (S4A-D22): todo opcional; `class_count: null` explícito es un
    cambio (pasar a `days`), un campo ausente no lo es (`model_fields_set`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SafeText | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    price_cop: StrictInt | None = Field(default=None, ge=PRICE_COP_MIN, le=PRICE_COP_MAX)
    kind: PlanKind | None = None
    duration_days: StrictInt | None = Field(
        default=None, ge=DURATION_DAYS_MIN, le=DURATION_DAYS_MAX
    )
    class_count: StrictInt | None = Field(default=None, ge=CLASS_COUNT_MIN, le=CLASS_COUNT_MAX)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanState:
    """Los campos editables del plan tras aplicar un `PlanPatch` (`service.merge_plan`)."""

    name: str
    price_cop: int
    kind: str
    duration_days: int
    class_count: int | None


class PlanOut(BaseModel):
    id: UUID
    name: str
    price_cop: int
    kind: PlanKind
    duration_days: int
    class_count: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    active_members_count: int  # S4A-D25: "Socios con él"


@dataclass(frozen=True)
class PlanSnapshot:
    """Lo que otros módulos saben de un plan (contrato de `service.get`)."""

    id: UUID
    name: str
    price_cop: int
    kind: str
    duration_days: int
    class_count: int | None
    is_active: bool
    deleted_at: datetime | None


class PlanListQuery(BaseModel):
    """Filtros de la lista de planes; el router los arma desde la query string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    q: str | None = Field(default=None, max_length=MAX_SEARCH_LENGTH, pattern=SEARCH_PATTERN)
    active: bool | None = None
