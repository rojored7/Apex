"""Contrato HTTP de la auditoría (S4A-B3, US-104; S4A-B4, US-102 y US-103).

- `VerifyResultOut` nunca lleva `before`, `after` ni `through_hash` (H-1: el ancla no se expone).
- `AuditListQuery` (S4A-D16, S4A-D46): filtros de `GET /audit`; `from` llega por alias (`from_`
  en Python); `table` con `TABLE_PATTERN` (dos segmentos en minúscula y guion bajo) y
  `TABLE_MAX_LENGTH`; `action` es el `Literal` de `core.audit.AuditAction`.
- `AuditRow` (lista): nunca `before` ni `after`. `user_email` y `user_name` son `None` si el
  `user_id` no está en `auth.users`.
- `AuditDetail` y `FieldChange` (S4A-D17, S4A-D52): todo valor `apx1.` sale como el marcador
  `{"encrypted": true, "key_id", "alg"}`; `FieldChange.encrypted` dice si el valor estaba cifrado.
- `MAX_AUDIT_OFFSET = 100_000` (S4A-D45: 422 `field="offset"`) y `MAX_SEQ = 2**63 - 1` (S4A-D46).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.audit import AuditAction
from app.core.pagination import MAX_SEARCH_LENGTH

MAX_AUDIT_OFFSET: Final = 100_000
MAX_SEQ: Final = 2**63 - 1
TABLE_PATTERN: Final = r"^[a-z_]{1,63}\.[a-z_]{1,63}$"
TABLE_MAX_LENGTH: Final = 127

ChangeKind = Literal["added", "removed", "changed"]


class VerifyResultOut(BaseModel):
    ok: bool
    rows_checked: int
    through_seq: int
    broken_at_seq: int | None
    started_at: datetime
    finished_at: datetime
    triggered_by: UUID
    source: Literal["api", "cli"]


class VerifyStartedOut(BaseModel):
    """Respuesta 202: la verificación sigue en segundo plano; `last` es la última terminada."""

    status: Literal["running"] = "running"
    last: VerifyResultOut | None


class AuditListQuery(BaseModel):
    """Filtros de `GET /audit` (S4A-D16, S4A-D46); el router la arma con sus parámetros."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    q: str | None = Field(default=None, max_length=MAX_SEARCH_LENGTH)
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    user_id: UUID | None = None
    table: str | None = Field(default=None, pattern=TABLE_PATTERN, max_length=TABLE_MAX_LENGTH)
    record_id: UUID | None = None
    subject_member_id: UUID | None = None
    action: AuditAction | None = None


class AuditRow(BaseModel):
    """Una fila de `GET /audit`: sin `before` ni `after` (S4A-D16)."""

    model_config = ConfigDict(extra="forbid")

    seq: int
    at: datetime
    user_id: UUID
    user_email: str | None
    user_name: str | None
    action: AuditAction
    table_name: str
    record_id: UUID | None
    subject_member_id: UUID | None


class FieldChange(BaseModel):
    """Un campo del diff (S4A-D17, S4A-D52); `before`/`after` ya con el marcador de blobs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    kind: ChangeKind
    before: Any = None
    after: Any = None
    encrypted: bool


class AuditDetail(AuditRow):
    """`GET /audit/{seq}` (S4A-D17): la fila completa, sin blobs (marcador) y con `changes`."""

    before: dict[str, Any] | None
    after: dict[str, Any] | None
    prev_hash: str
    hash: str
    changes: list[FieldChange]
