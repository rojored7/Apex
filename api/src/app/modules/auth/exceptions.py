"""Errores del módulo auth con el envelope de US-017 (contrato público, importable)."""

from __future__ import annotations

from app.core.errors import DomainError


class AuthError(DomainError):
    """Regla de cuentas incumplida. Códigos: `member_id_required`, `member_id_not_allowed`,
    `weak_password`, `user_not_found`."""

    status = 422
    code = "auth_error"
    default_message = "La cuenta no es válida."


class InvalidCredentials(DomainError):
    """Login rechazado: el mismo 401 para las cinco causas (correo inexistente, contraseña
    errada, cuenta bloqueada, inactiva o pendiente de activación); no revela cuál."""

    status = 401
    code = "invalid_credentials"
    default_message = "Correo o contraseña incorrectos."


class InvalidRefresh(DomainError):
    """Refresh rechazado (sin cookie, vencido, revocado, reusado o de una cuenta que ya no
    puede autenticarse). El router le agrega el `Set-Cookie` que borra la cookie, salvo con
    `clear_cookie = False`: un rotado dentro de la gracia (M-2), cuyo sucesor ya viaja en la
    respuesta de la petición concurrente."""

    status = 401
    code = "invalid_refresh"
    default_message = "La sesión ya no es válida. Inicia sesión de nuevo."
    clear_cookie: bool = True
