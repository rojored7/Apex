"""Errores de dominio de socios (S2-B7, US-069). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido (documento, teléfono o correo).
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class MemberError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "member_error"
    default_message = "Los datos del socio no son válidos."


class MemberValidationError(MemberError):
    """Regla de entrada incumplida (nombres vacíos, sexo, fecha futura, valor que se normaliza a
    vacío, L-3): 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos del socio no son válidos."


class MemberDocumentDuplicated(MemberError):
    """Ya hay un socio no borrado con ese documento (`uq_members_document_idx_alive`): 409 con
    `field="document"` y `existing_id` (L-1 de la revisión: aceptable)."""

    status = 409
    code = "member_document_duplicated"
    default_message = "Ya existe un socio con este documento"

    def __init__(self, existing_id: UUID | None = None) -> None:
        super().__init__(field="document", existing_id=existing_id)


class MemberNotFound(MemberError):
    """El socio no existe (o está dado de baja cuando no se piden los borrados)."""

    status = 404
    code = "member_not_found"
    default_message = "No se encontró el socio."


# S3-B10 (US-075, US-076; D21, M-3, S3-D46, S3-D70) --------------------------------------


class MemberIsDeactivated(MemberError):
    """Editar a un socio dado de baja (su ficha es de solo lectura, N-20). El evento de la baja
    se llama `MemberDeactivated` (S3-D70, L-7): nombres distintos a propósito."""

    status = 409
    code = "member_deactivated"
    default_message = "El socio está dado de baja; reactívalo para editarlo."


class MemberFieldForbidden(MemberError):
    """Un rol que no es admin envía `document` o `document_type` (por presencia, M-3)."""

    status = 403
    code = "forbidden_field"
    default_message = "No tienes permiso para cambiar este campo."

    def __init__(self, field: str) -> None:
        super().__init__(field=field)


class MemberAlreadyDeactivated(MemberError):
    """Dar de baja a un socio que ya lo está."""

    status = 409
    code = "member_already_deactivated"
    default_message = "El socio ya está dado de baja."


class MemberNotDeactivated(MemberError):
    """Reactivar a un socio que no está dado de baja."""

    status = 409
    code = "member_not_deactivated"
    default_message = "El socio no está dado de baja."


class ConsentCannotBeWithdrawn(MemberError):
    """`data_consent=false` en la edición: retirar la autorización es otro proceso (Ley 1581,
    S3-D46). 422 con `field="data_consent"`."""

    status = 422
    code = "consent_cannot_be_withdrawn"
    default_message = "La autorización de datos no se retira desde la edición del socio."

    def __init__(self) -> None:
        super().__init__(field="data_consent")
