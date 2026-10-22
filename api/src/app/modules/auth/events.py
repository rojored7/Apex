"""Eventos de dominio de auth (revisión Python H1: salen de `service.py`). Privado del módulo.

`audit/service.py` y el CLI los importan desde `auth.service`, que los reexporta (regla de
módulos 2: otro módulo solo ve el `service.py`). Ningún evento lleva el correo tecleado, la
contraseña ni un token (N-31).

- `UserCreated` (seed y `create_user`), `LoginAttempted` (cada intento sobre una cuenta
  existente, con IP y agente truncado; L-8), `SessionsRevoked` (con el motivo y cuántas),
  `UserLocked` (por un admin o por fallos) y `PasswordChanged` (con `via_link_issued_by`,
  L-13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.core.events import DomainEvent

LoginFailureReason = Literal["bad_password", "locked", "inactive", "pending"]


RevokeReason = Literal[
    "admin", "lock", "delete", "refresh_reuse", "password_changed", "password_reset"
]


PasswordChangeVia = Literal["change", "activate", "reset"]


# Eventos -------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class UserCreated(DomainEvent):
    user_id: UUID
    role: str
    by: UUID


@dataclass(frozen=True, kw_only=True)
class LoginAttempted(DomainEvent):
    """Intento de login sobre una cuenta existente (nunca lleva el correo tecleado; N-31)."""

    user_id: UUID
    result: Literal["ok", "failed"]
    reason: LoginFailureReason | None = None
    ip: str
    user_agent: str | None = None


@dataclass(frozen=True, kw_only=True)
class SessionsRevoked(DomainEvent):
    user_id: UUID
    by: UUID
    revoked: int
    reason: RevokeReason


@dataclass(frozen=True, kw_only=True)
class UserLocked(DomainEvent):
    user_id: UUID
    by: UUID
    reason: Literal["admin", "too_many_failures"]


@dataclass(frozen=True, kw_only=True)
class PasswordChanged(DomainEvent):
    """Contraseña nueva (US-046, US-048). `via_link_issued_by` es el `created_by` del enlace
    con que se fijó (L-13); `None` en un cambio desde "Mi cuenta"."""

    user_id: UUID
    by: UUID
    via: PasswordChangeVia
    via_link_issued_by: UUID | None = None


__all__ = [
    "LoginAttempted",
    "LoginFailureReason",
    "PasswordChangeVia",
    "PasswordChanged",
    "RevokeReason",
    "SessionsRevoked",
    "UserCreated",
    "UserLocked",
]
