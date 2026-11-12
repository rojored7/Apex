"""Contrato de adjuntos (S6-C1; S6-D18, S6-D22). Stub: nunca devuelve `filename_random`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

KIND = Literal["photo", "consent", "other"]
MIME = Literal["image/jpeg", "image/png", "application/pdf"]


class AttachmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    owner_table: str
    owner_id: UUID
    kind: KIND
    mime: MIME
    size_bytes: int
    sensitive: bool
    uploaded_by: UUID
    created_at: datetime


@dataclass(frozen=True)
class AttachmentBody:
    """Metadatos más el cuerpo: `data` (sensibles, descifrado en memoria) o `stream` (foto)."""

    meta: AttachmentOut
    data: bytes | None = None
    stream: AsyncIterator[bytes] | None = None
