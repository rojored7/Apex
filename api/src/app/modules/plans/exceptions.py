"""Errores de dominio de planes (S2-B9, US-078 y US-079). Salen por el handler de `DomainError`.

Ningún `message` repite el valor recibido.
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class PlanError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "plan_error"
    default_message = "Los datos del plan no son válidos."


class PlanValidationError(PlanError):
    """Regla de entrada incumplida (`class_count` según `kind`, topes de duración y de clases):
    422 con `field`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos del plan no son válidos."


class PlanNameDuplicated(PlanError):
    """Ya hay un plan vivo con ese nombre sin distinguir mayúsculas ni espacios de los extremos
    (`uq_plans_name_alive`, DECISIÓN 32): 409 con `field="name"` y `existing_id`."""

    status = 409
    code = "plan_name_duplicated"
    default_message = "Ya existe un plan con este nombre"

    def __init__(self, existing_id: UUID | None = None) -> None:
        super().__init__(field="name", existing_id=existing_id)


class PlanNotFound(PlanError):
    """El plan no existe o está dado de baja."""

    status = 404
    code = "plan_not_found"
    default_message = "No se encontró el plan."


class PlanScopeForbidden(PlanError):
    """Fuera del alcance del rol (S2-D26): el coach solo ve planes activos."""

    status = 403
    code = "forbidden"
    default_message = "No tienes permiso para esta acción."


class PlanHasActiveMemberships(PlanError):
    """S4A-D24 (US-082): la baja de un plan con membresías activas (estado efectivo distinto de
    `cancelled` y `expired`, incluidas `pending_payment` y `frozen`). 409 con solo el conteo
    (S4A-D60, L-9): ni ids ni nombres."""

    status = 409
    code = "plan_has_active_memberships"
    default_message = "Este plan tiene membresías activas, desactívalo en su lugar."

    def __init__(self, count: int) -> None:
        self.count = count
        palabra = "membresía activa" if count == 1 else "membresías activas"
        super().__init__(message=f"Este plan tiene {count} {palabra}, desactívalo en su lugar.")
