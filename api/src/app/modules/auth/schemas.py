"""Schemas públicos de auth (US-041 T7). `UserOut` nunca expone `password_hash`."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

Role = Literal["admin", "coach", "member"]
UserStatus = Literal["active", "inactive", "locked", "deleted"]


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    email: str
    role: Role
    member_id: UUID | None
    status: UserStatus
