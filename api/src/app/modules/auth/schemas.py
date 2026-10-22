"""Schemas públicos de auth (US-041 T7; S2-B2 US-042/043/044; S2-B3 US-045/046/047).

`UserOut` y `UserRow` nunca exponen `password_hash` y ninguna salida trae el refresh: viaja
solo en la cookie `HttpOnly`. `CreateUserIn.role` admite solo `admin` y `coach`, sin
`member_id`, hasta el portal (L-2, S2-D42). `POST /auth/me/password` responde
`AccessTokenOut` con un access nuevo (S2-D37, H-3). `CreateUserOut.activation_url` viaja una
sola vez (blueprint 7.2). S2-B4: `ResetIn`, `ForgotIn` e `IssuedLinkOut` (`extra="forbid"`).
S2-B5: `UpdateUserIn` (`extra="forbid"`; un campo ausente o nulo no cambia) y `RevokeSessionsOut`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.core.validators import EmailAddress

Role = Literal["admin", "coach", "member"]
# L-2: el alta de cuentas por el panel no crea socios hasta el portal (v1.0).
StaffRole = Literal["admin", "coach"]
# S2-D1: orden de precedencia `deleted > locked > inactive > pending_activation > active`.
UserStatus = Literal["active", "inactive", "locked", "pending_activation", "deleted"]


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    email: str
    role: Role
    member_id: UUID | None
    status: UserStatus
    must_change_password: bool


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


class MeOut(BaseModel):
    """`GET /auth/me` (S2-D14): el usuario vigente y el nombre del gimnasio."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    role: Role
    member_id: UUID | None
    gym_name: str
    must_change_password: bool


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    # M5 de la revisión general: el contrato publica `minLength: 12`, igual que el front.
    new_password: SecretStr = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class AccessTokenOut(BaseModel):
    """Access nuevo tras cambiar la contraseña (S2-D37): el anterior queda cortado."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - tipo de token, no un secreto
    expires_in: int


class UserRow(BaseModel):
    """Fila de `GET /users`; `active_sessions` cuenta refresh vigentes y no revocados."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    role: Role
    status: UserStatus
    member_id: UUID | None
    last_login_at: datetime | None
    created_at: datetime
    active_sessions: int


class CreateUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress
    role: StaffRole


class CreateUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserOut
    activation_url: str
    expires_at: datetime


# S2-B4 · activación, recuperación y reenvío (US-048, US-052) ------------------------------

OneTimePurposeOut = Literal["activate", "reset"]
RESET_TOKEN_MIN_LENGTH = 20
RESET_TOKEN_MAX_LENGTH = 200


class ResetIn(BaseModel):
    """`POST /auth/reset`: el token del enlace y la contraseña nueva (activa o restablece)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=RESET_TOKEN_MIN_LENGTH, max_length=RESET_TOKEN_MAX_LENGTH)
    new_password: SecretStr = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class ForgotIn(BaseModel):
    """`POST /auth/forgot`: solo el correo (hasta 254); la respuesta es siempre 204 (H-2)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailAddress


class IssuedLinkOut(BaseModel):
    """`POST /users/{id}/resend-link` (y `cli issue-reset-link`): el enlace viaja una sola vez."""

    model_config = ConfigDict(extra="forbid")

    url: str
    purpose: OneTimePurposeOut
    expires_at: datetime


# S2-B5 · ciclo de vida del usuario (US-049, US-050, US-051) -------------------------------


class UpdateUserIn(BaseModel):
    """`PATCH /users/{user_id}`: correo y rol; un campo ausente o nulo no cambia (US-049)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailAddress | None = None
    role: Role | None = None


class RevokeSessionsOut(BaseModel):
    """`POST /users/{user_id}/revoke-sessions`: cuántos refresh se revocaron (puede ser 0)."""

    model_config = ConfigDict(extra="forbid")

    revoked: int
