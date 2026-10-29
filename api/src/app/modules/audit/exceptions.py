"""Errores de dominio de la auditoría (S4A-B3, US-104; S4A-B4, US-102 y US-103). Salen por el
handler de `DomainError`."""

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


class AuditEntryNotFound(AuditError):
    """`GET /audit/{seq}` con un `seq` que no existe (S4A-D17): 404 `audit_entry_not_found`."""

    status = 404
    code = "audit_entry_not_found"
    default_message = "No existe ese registro de auditoría."


class AuditRangeInvalid(AuditError):
    """Filtro de `GET /audit` fuera de rango (S4A-D45, S4A-D46): `from`/`to` fuera de
    `[INSTANT_FLOOR, now + 1 día]` o invertidos, u `offset` mayor que `MAX_AUDIT_OFFSET`. 422
    `validation_error` con el `field` que falla y sin el valor en el mensaje."""

    status = 422
    code = "validation_error"
    default_message = "El filtro de la auditoría no es válido."
