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


class SessionDuplicate(ClassError):
    """Ya existe una sesión extra no cancelada con ese inicio y ese coach (S7-D38): 409."""

    status = 409
    code = "session_duplicate"
    default_message = "Ya existe una sesión extra con ese horario y ese coach."


class AlreadyCheckedIn(ClassError):
    """El socio ya tiene asistencia viva en la sesión (RN-10, US-159 CA4): 409."""

    status = 409
    code = "already_checked_in"
    default_message = "El socio ya registró asistencia en esta clase."


class CheckinSessionCancelled(ClassError):
    """No hay check-in en una sesión cancelada (US-159 CA5): 409."""

    status = 409
    code = "session_cancelled"
    default_message = "La sesión está cancelada."


class AttendanceNotFound(ClassError):
    """No hay asistencia viva con ese id (nunca existió o ya se quitó; US-161 CA3): 404."""

    status = 404
    code = "attendance_not_found"
    default_message = "No existe esa asistencia."


class AttendanceLocked(ClassError):
    """El coach solo quita asistencias de sesiones de hoy o de ayer en Bogotá (S7-D27 b): 403."""

    status = 403
    code = "attendance_locked"
    default_message = "Solo un administrador puede quitar la asistencia de una clase de otro día."


class MembershipPortNotRegistered(RuntimeError):
    """Nadie registró el puerto de membresías (S7-D6): el check-in falla cerrado y no escribe."""
