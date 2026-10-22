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
