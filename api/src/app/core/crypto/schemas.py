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

OpVerb = Literal[
    "encrypt", "decrypt", "index", "sign", "verify", "wrap", "unwrap", "rotate", "export"
]
JobKind = Literal["rotate", "reencrypt", "migrate_provider", "rewrap"]


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


class CryptoOpOut(BaseModel):
    """Una fila de la bitácora (S6-D16, S6-B2). Nunca lleva material, referencias ni detalle de
    error del proveedor."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    at: datetime
    user_id: UUID
    verb: OpVerb
    data_class: str | None
    key_id: UUID | None
    key_version: int | None
    record_id: UUID | None
    purpose: str | None
    result: Literal["ok", "error"]
    batch_id: UUID | None
    count: int


class CryptoJobOut(BaseModel):
    """Un trabajo de rotación o recifrado con su avance (S6-D16, S6-B2). Sin el texto `error`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    kind: JobKind
    data_class: str | None
    status: Literal["pending", "running", "done", "failed"]
    total: int
    done: int
    percent: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class OpsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: datetime | None = None
    end: datetime | None = None
    verb: OpVerb | None = None
    data_class: str | None = None
    key_id: UUID | None = None
    user_id: UUID | None = None
    result: Literal["ok", "error"] | None = None
    batch_id: UUID | None = None
    q: str | None = None


class JobsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["pending", "running", "done", "failed"] | None = None
    kind: JobKind | None = None
    data_class: str | None = None
    q: str | None = None
