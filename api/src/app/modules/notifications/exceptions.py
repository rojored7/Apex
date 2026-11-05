"""Errores de dominio de `notifications` (S5-B6, US-120 y US-121). Salen por el handler de
`DomainError`. Ningún `message` repite el valor recibido."""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class NotificationError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "notification_error"
    default_message = "La operación de avisos no es válida."


class TemplateError(NotificationError):
    """Plantilla mal formada: variable desconocida o ausente del contexto, llave sin cerrar o
    sintaxis de formato no permitida. 422 con `field` (`subject` o `body`) cuando se valida."""

    status = 422
    code = "validation_error"
    default_message = "La plantilla tiene variables o llaves no válidas."


class RuleValidationError(NotificationError):
    """Regla incumplida (disparador, canal, signo del desfase, plantilla): 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos de la regla no son válidos."


class TemplateNotFound(NotificationError):
    status = 404
    code = "template_not_found"
    default_message = "No se encontró la plantilla."


class RuleNotFound(NotificationError):
    status = 404
    code = "rule_not_found"
    default_message = "No se encontró la regla."


class TemplateNameTaken(NotificationError):
    """Ya hay una plantilla con ese nombre (`uq_notification_templates_name`)."""

    status = 409
    code = "template_name_taken"
    default_message = "Ya existe una plantilla con este nombre."

    def __init__(self, existing_id: UUID | None = None) -> None:
        super().__init__(field="name", existing_id=existing_id)


class DuplicateActiveRule(NotificationError):
    """Ya hay una regla activa con ese disparador, desfase y canal."""

    status = 409
    code = "duplicate_active_rule"
    default_message = "Ya existe una regla activa con ese disparador, desfase y canal."

    def __init__(self, existing_id: UUID | None = None) -> None:
        super().__init__(existing_id=existing_id)


class SeedInProgress(NotificationError):
    """La siembra chocó con otra que corre a la vez (S5-D215). Texto fijo; reintentable."""

    status = 409
    code = "seed_in_progress"
    default_message = "siembra en curso por otro proceso; reintente"


class NotificationNotFound(NotificationError):
    status = 404
    code = "notification_not_found"
    default_message = "No se encontró el aviso."


class NotificationClosed(NotificationError):
    """El aviso ya está `sent` o `skipped` y no se puede omitir, o está `skipped` y se pide su
    enlace de WhatsApp (S5-B7, US-129)."""

    status = 409
    code = "notification_closed"
    default_message = "El aviso ya está cerrado."


class WrongChannel(NotificationError):
    """Se pidió el enlace de WhatsApp de un aviso que no es de ese canal (S5-D27)."""

    status = 409
    code = "wrong_channel"
    default_message = "El aviso no es de WhatsApp."


class MemberWithoutPhone(NotificationError):
    """El socio no tiene teléfono guardado: no hay enlace de WhatsApp posible (S5-D27)."""

    status = 422
    code = "member_without_phone"
    default_message = "El socio no tiene teléfono."


class InvalidPhone(NotificationError):
    """El teléfono guardado no es un celular colombiano (S5-D224). Texto fijo: nunca repite el
    número."""

    status = 422
    code = "invalid_phone"
    default_message = "El teléfono del socio no es un celular válido."


class ChannelDisabled(NotificationError):
    """El canal del aviso está deshabilitado en `settings.channels` (S5-D265b). Texto fijo."""

    status = 409
    code = "channel_disabled"
    default_message = "El canal del aviso está deshabilitado."
