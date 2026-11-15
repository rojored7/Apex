"""Errores de dominio de `results` (S8-B1, US-169). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido.
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class ResultsError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "results_error"
    default_message = "Los datos del resultado no son válidos."


class ResultValidationError(ResultsError):
    """Regla de entrada incumplida: 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos del resultado no son válidos."


class WodNotScored(ResultsError):
    """El WOD es «sin puntaje» (`score_type = none`): no admite resultados (S8-D7)."""

    status = 422
    code = "wod_not_scored"
    default_message = "Este WOD no registra resultados."

    def __init__(self) -> None:
        super().__init__(field="wod_id")


class ResultExists(ResultsError):
    """El socio ya tiene un resultado vigente en el WOD (RN-11): 409 con `existing_id`."""

    status = 409
    code = "result_exists"
    default_message = "El socio ya tiene un resultado en este WOD."

    def __init__(self, existing_id: UUID | None) -> None:
        super().__init__(existing_id=existing_id)


class InvalidSupersedes(ResultsError):
    """`supersedes_id` no es el resultado vigente de ese socio en ese WOD (S8-D11): 409."""

    status = 409
    code = "invalid_supersedes"
    default_message = "El resultado que se quiere corregir no es el vigente."

    def __init__(self) -> None:
        super().__init__(field="supersedes_id")
