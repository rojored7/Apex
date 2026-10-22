"""Errores del módulo auth con el envelope de US-017 (contrato público, importable).

S2-B3: `EmailTaken` (409) e `InvalidCurrentPassword` (422).
"""

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


class EmailTaken(DomainError):
    """Alta con un correo de una cuenta no borrada (S2-B3, US-047). Lleva `field="email"` y
    `existing_id`; una cuenta borrada libera el correo (`uq_users_email_alive`)."""

    status = 409
    code = "email_taken"
    default_message = "Ya existe una cuenta con este correo."


class InvalidCurrentPassword(DomainError):
    """`POST /auth/me/password` con la contraseña actual errada (S2-B3, US-046). Lleva
    `field="current_password"` y no cambia nada."""

    status = 422
    code = "invalid_current_password"
    default_message = "La contraseña actual no es correcta."
