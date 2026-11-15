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


class WodNotFound(WodsError):
    """El WOD no existe."""

    status = 404
    code = "wod_not_found"
    default_message = "No se encontró el WOD."


class WodDateTaken(WodsError):
    """Ya hay un WOD para esa fecha (US-166 CA5, S8-D7): 409 con `existing_id`."""

    status = 409
    code = "wod_date_taken"
    default_message = "Ya existe un WOD para esa fecha."

    def __init__(self, existing_id: UUID | None) -> None:
        super().__init__(field="date", existing_id=existing_id)


class ScoreTypeMismatch(WodsError):
    """El tipo de marca no es el del benchmark elegido (S8-D7): 422 con `field`."""

    status = 422
    code = "score_type_mismatch"
    default_message = "El tipo de marca debe ser el del benchmark elegido."

    def __init__(self) -> None:
        super().__init__(field="score_type")


class LockedByResults(WodsError):
    """El WOD ya tiene resultados: `date`, `time_cap_s` y `benchmark_id` no cambian (S8-D7)."""

    status = 422
    code = "locked_by_results"
    default_message = "El WOD ya tiene resultados: este campo no se puede cambiar."

    def __init__(self, field: str) -> None:
        super().__init__(field=field)


class ResultsProbeNotRegistered(RuntimeError):
    """Nadie registró el puerto `ResultsProbe`: lo que depende de resultados falla cerrado."""
