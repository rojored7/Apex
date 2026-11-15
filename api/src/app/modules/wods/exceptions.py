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


class BenchmarkExists(WodsError):
    """Ya hay un benchmark con ese nombre normalizado (US-166): 409 con `existing_id`."""

    status = 409
    code = "benchmark_exists"
    default_message = "Ya existe un benchmark con ese nombre."

    def __init__(self, existing_id: UUID | None) -> None:
        super().__init__(field="name", existing_id=existing_id)


class BenchmarkNotFound(WodsError):
    """El benchmark no existe."""

    status = 404
    code = "benchmark_not_found"
    default_message = "No se encontró el benchmark."


class ScoreTypeLocked(WodsError):
    """El benchmark ya lo usan WODs: su tipo de marca no cambia (S8-D6): 422 con `field`."""

    status = 422
    code = "score_type_locked"
    default_message = "El tipo de marca no se puede cambiar: ya hay WODs que usan este benchmark."

    def __init__(self) -> None:
        super().__init__(field="score_type")
