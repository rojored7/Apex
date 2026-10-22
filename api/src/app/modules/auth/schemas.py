"""Schemas públicos de auth (US-041 T7; S2-B2 US-042/043/044). `UserOut` nunca expone
`password_hash` y ninguna salida trae el refresh: viaja solo en la cookie `HttpOnly`."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.security import PASSWORD_MAX_LENGTH
from app.core.validators import EmailAddress

Role = Literal["admin", "coach", "member"]
# S2-D1: orden de precedencia `deleted > locked > inactive > pending_activation > active`.
UserStatus = Literal["active", "inactive", "locked", "pending_activation", "deleted"]


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    email: str
    role: Role
    member_id: UUID | None
    status: UserStatus


class UserSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    email: str
    role: Role


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress
    password: SecretStr = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class LoginOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - tipo de token, no un secreto
    expires_in: int
    user: UserSummary
    must_change_password: bool


class RefreshOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - tipo de token, no un secreto
    expires_in: int
