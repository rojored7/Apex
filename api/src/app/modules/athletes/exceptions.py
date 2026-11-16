"""Errores de dominio de `athletes` (S9-A1, US-178). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido ni un dato de salud (S9-D4, L-2).
"""

from __future__ import annotations

from app.core.errors import DomainError


class AthletesError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "athletes_error"
    default_message = "Los datos del atleta no son válidos."


class MetricValidationError(AthletesError):
    """Regla de entrada incumplida (rango, fecha, ninguna medida): 422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos de la medida no son válidos."


class ConsentRequired(AthletesError):
    """El socio no tiene autorización de datos vigente (S9-D29, H-1): 409 `consent_required`."""

    status = 409
    code = "consent_required"
    default_message = "Registra primero la autorización de datos del socio."


class MetricNotFound(AthletesError):
    """La medición no existe o es de otro socio (S9-D15): 404 `metric_not_found`."""

    status = 404
    code = "metric_not_found"
    default_message = "No se encontró la medición."


class MetricVoided(AthletesError):
    """La medición está anulada y no se revela (S9-D15, L-2): 409 `metric_voided`."""

    status = 409
    code = "metric_voided"
    default_message = "La medición está anulada."
