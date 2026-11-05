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


# S4A-B6 (US-077; S4A-D21, S4A-D50) ------------------------------------------------------------


class InvalidPurpose(MemberError):
    """`contact_for_notification` con un propósito que no es `notify` ni `auth_link`. Se lanza
    antes de leer la base; no sale por HTTP (ninguna ruta llama al contacto)."""

    code = "invalid_purpose"
    default_message = "El propósito de la consulta de contacto no es válido."


class MemberNotContactable(MemberError):
    """El socio no existe o está dado de baja: no se descifra nada ni se audita."""

    code = "member_not_contactable"
    default_message = "El socio no se puede contactar."


class ConsentCannotBeWithdrawn(MemberError):
    """`data_consent=false` en la edición: retirar la autorización es otro proceso (Ley 1581,
    S3-D46). 422 con `field="data_consent"`."""

    status = 422
    code = "consent_cannot_be_withdrawn"
    default_message = "La autorización de datos no se retira desde la edición del socio."

    def __init__(self) -> None:
        super().__init__(field="data_consent")


# S5-B5 (US-123; S5-D31, S5-D32, N-20) ------------------------------------------------------


class MemberDeleted(MemberError):
    """Cambiar las preferencias de canal de un socio dado de baja (N-20): su ficha es de solo
    lectura. `GET` sí responde (200); `PATCH` da 409 `member_deleted`."""

    status = 409
    code = "member_deleted"
    default_message = "El socio está dado de baja; reactívalo para cambiar sus canales."


class InvalidField(MemberError):
    """`contact_for_notification` con un campo que no es `phone` ni `email` en `fields`. Se lanza
    antes de leer la base; no sale por HTTP (ninguna ruta llama al contacto)."""

    code = "invalid_field"
    default_message = "El campo de contacto pedido no es válido."


class ConsentRequired(MemberError):
    """Activar el correo de un socio sin `data_consent_at` (S5-D211, Ley 1581): el opt-in no se
    guarda sin base legal. 422; `whatsapp_link` sí se puede desactivar sin autorización."""

    status = 422
    code = "consent_required"
    default_message = "El socio no autorizó el uso de sus datos; no se puede activar el correo."


class MemberContactUnreadable(MemberError):
    """El dato cifrado de ESE socio no se puede abrir (blob corrupto, etiqueta inválida, llave de
    la fila retirada o desconocida; S5-D230). No es un fallo del custodio: `CryptoUnavailable`
    (sellado, inalcanzable, sin permiso) sigue subiendo tal cual. El mensaje no dice qué campo."""

    status = 422
    code = "member_contact_unreadable"
    default_message = "El contacto del socio no se puede leer."
