"""Contrato HTTP de la verificación de la cadena (S4A-B3, US-104; S4A-D14).

`VerifyResultOut` nunca lleva `before`, `after` ni `through_hash` (H-1: el ancla no se expone).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
