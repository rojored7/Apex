"""Errores de dominio de la auditoría (S4A-B3, US-104). Salen por el handler de `DomainError`."""

from __future__ import annotations

from app.core.errors import DomainError


class AuditError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "audit_error"
    default_message = "No se pudo completar la operación de auditoría."


class VerificationRunning(AuditError):
    """Otra verificación tiene el candado `4_270_003` (S4A-D13): 409 `verification_running`."""

    status = 409
    code = "verification_running"
    default_message = "Ya hay una verificación de la cadena en curso; espera a que termine."
