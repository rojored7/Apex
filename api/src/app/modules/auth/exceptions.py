"""Errores del módulo auth con el envelope de US-017 (contrato público, importable)."""

from __future__ import annotations

from app.core.errors import DomainError


class AuthError(DomainError):
    """Regla de cuentas incumplida. Códigos: `member_id_required`, `member_id_not_allowed`,
    `weak_password`, `user_not_found`."""

    status = 422
    code = "auth_error"
    default_message = "La cuenta no es válida."
