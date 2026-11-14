"""Errores de dominio de clases (S7-D20; US-155). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido.
"""

from __future__ import annotations

from app.core.errors import DomainError


class ClassError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "class_error"
    default_message = "Los datos de la clase no son válidos."


class ClassValidationError(ClassError):
    """Regla de entrada incumplida (días, duración, cupo, nombre): 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos de la franja no son válidos."


class SlotConflict(ClassError):
    """Ya hay una franja activa que comparte día y hora de inicio (US-155 CA3): 409."""

    status = 409
    code = "slot_conflict"
    default_message = "Ya hay una franja activa a esa hora en alguno de esos días."


class CoachInvalid(ClassError):
    """`default_coach_id` no es un usuario activo con rol coach o admin (S7-D7): 422."""

    status = 422
    code = "coach_invalid"
    default_message = "El coach debe ser un usuario activo con rol coach o admin."

    def __init__(self) -> None:
        super().__init__(field="default_coach_id")


class SlotNotFound(ClassError):
    """La franja no existe."""

    status = 404
    code = "slot_not_found"
    default_message = "No se encontró la franja."


class SessionNotFound(ClassError):
    """La sesión no existe."""

    status = 404
    code = "session_not_found"
    default_message = "No se encontró la sesión."


class SessionAlreadyCancelled(ClassError):
    """La sesión ya estaba cancelada (US-157 CA5): 409."""

    status = 409
    code = "session_already_cancelled"
    default_message = "La sesión ya está cancelada."


class SessionFinished(ClassError):
    """La sesión ya terminó: no se cancela (S7-D32, L-5): 409."""

    status = 409
    code = "session_finished"
    default_message = "La sesión ya terminó y no se puede cancelar."


class RangeTooLong(ClassError):
    """El rango `from`/`to` supera los 62 días (S7-D20): 422."""

    status = 422
    code = "range_too_long"
    default_message = "El rango no puede pasar de 62 días."

    def __init__(self) -> None:
        super().__init__(field="to")
