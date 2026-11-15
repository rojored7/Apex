"""Errores de dominio de `wods` (S8-A1, US-165). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido.
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class WodsError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "wods_error"
    default_message = "Los datos del entrenamiento no son válidos."


class WodsValidationError(WodsError):
    """Regla de entrada incumplida: 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos del movimiento no son válidos."


class MovementExists(WodsError):
    """Ya hay un movimiento con ese nombre normalizado (US-165 CA2): 409 con `existing_id`."""

    status = 409
    code = "movement_exists"
    default_message = "Ya existe un movimiento con ese nombre."

    def __init__(self, existing_id: UUID | None) -> None:
        super().__init__(field="name", existing_id=existing_id)


class MovementNotFound(WodsError):
    """El movimiento no existe."""

    status = 404
    code = "movement_not_found"
    default_message = "No se encontró el movimiento."
