"""Errores del módulo auth con el envelope de US-017 (contrato público, importable).

S2-B3: `EmailTaken` (409) e `InvalidCurrentPassword` (422).
S2-B4: `InvalidToken` (400), `UserNotEligible` (409) y `UserNotFound` (404).
S2-B5: `LastAdmin`, `CannotLockSelf`, `AlreadyLocked` y `NotLocked` (409).
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


INVALID_TOKEN_MESSAGE = "El enlace ya no es válido. Pide uno nuevo al administrador."  # noqa: S105


class InvalidToken(DomainError):
    """`POST /auth/reset` con un token inexistente, usado, vencido o de una cuenta que ya no
    puede usarlo (S2-B4, US-048): el mismo 400 y el mismo texto para todas las causas."""

    status = 400
    code = "invalid_token"
    default_message = INVALID_TOKEN_MESSAGE


class UserNotEligible(DomainError):
    """`resend-link` sobre una cuenta bloqueada o borrada, sobre la propia cuenta del emisor o
    sobre otro admin activo con contraseña (S2-B4, US-052; L-13), y `PATCH /users/{id}` que
    cambia el correo de otro admin activo con contraseña (revisión de seguridad V10, N-8)."""

    status = 409
    code = "user_not_eligible"
    default_message = "Esta cuenta no puede recibir un enlace nuevo."


class UserNotFound(DomainError):
    """Cuenta inexistente o el usuario técnico (`SYSTEM_USER_ID`, N-15) (S2-B4)."""

    status = 404
    code = "user_not_found"
    default_message = "No se encontró la cuenta."


class LastAdmin(DomainError):
    """Baja, cambio de rol o bloqueo que dejaría el sistema sin un admin activo (S2-B5, US-049,
    US-050). El técnico (`SYSTEM_USER_ID`) nunca cuenta como admin activo."""

    status = 409
    code = "last_admin"
    default_message = "Debe quedar al menos un administrador activo."


class CannotLockSelf(DomainError):
    """Un admin intenta bloquear su propia cuenta (S2-B5, US-050)."""

    status = 409
    code = "cannot_lock_self"
    default_message = "No puedes bloquear tu propia cuenta."


class AlreadyLocked(DomainError):
    """`lock` sobre una cuenta ya bloqueada (S2-B5, US-050)."""

    status = 409
    code = "already_locked"
    default_message = "La cuenta ya está bloqueada."


class NotLocked(DomainError):
    """`unlock` sobre una cuenta que no está bloqueada (S2-B5, US-050)."""

    status = 409
    code = "not_locked"
    default_message = "La cuenta no está bloqueada."
