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


class LeaderboardTooLarge(ResultsError):
    """El WOD tiene más resultados vigentes que `LEADERBOARD_MAX_ROWS` (S8-D13, L-6): un ranking
    nunca se trunca, se rechaza."""

    status = 422
    code = "leaderboard_too_large"
    default_message = "El WOD tiene demasiados resultados para armar el leaderboard."


class ResultNotFound(ResultsError):
    """El resultado no existe (S8-D46 b): 404."""

    status = 404
    code = "result_not_found"
    default_message = "No se encontró el resultado."


class ResultAlreadyVoided(ResultsError):
    """El resultado ya estaba anulado (S8-D46 b): 409."""

    status = 409
    code = "result_already_voided"
    default_message = "El resultado ya está anulado."


class ResultNotVoidable(ResultsError):
    """Solo se anula un resultado vigente y validado; uno corregido o pendiente no (S8-D46 b)."""

    status = 409
    code = "result_not_voidable"
    default_message = "Solo se puede anular el resultado vigente y validado."
