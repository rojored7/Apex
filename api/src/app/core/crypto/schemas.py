"""DTO del router de llaves (S6-D13, S6-B1).

Nunca llevan `wrapped_material` ni la referencia interna de las filas `sign`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.crypto.state import CryptoState
from app.core.pagination import Page


class CryptoKeyOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    purpose: Literal["encrypt", "index", "sign"]
    data_class: str
    algorithm: str
    version: int
    state: Literal["active", "decrypt_only", "retired"]
    provider: Literal["local", "openbao"]
    created_at: datetime
    rotated_at: datetime | None
    age_days: int
    records_count: int | None


class ProviderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: list[str]
    state: CryptoState


class KeysSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_count: int
    operations_today: int
    running_jobs: int
    provider: ProviderSummary


class KeysPage(Page[CryptoKeyOut]):
    """`Page` de llaves más el bloque `summary` (S6-D13)."""

    summary: KeysSummary


class KeysFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: Literal["encrypt", "index", "sign"] | None = None
    state: Literal["active", "decrypt_only", "retired"] | None = None
    provider: Literal["local", "openbao"] | None = None
    data_class: str | None = None
    q: str | None = None
