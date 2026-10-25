"""Errores de dominio de membresías (S3-B1, US-084; D34). Salen por el handler de `DomainError`.

Ningún `message` repite valores del usuario. El 404 del socio es `MemberNotFound` de
`members.exceptions` (S3-C10): no se duplica aquí.

Todos conservan la firma de `DomainError` (`code`, `message`, `field`, `existing_id`, `status`):
`sell.reraise_with_prefix` (B4, E5) construye copias con `type(error)(...)`.
"""

from __future__ import annotations

from uuid import UUID

from app.core.errors import DomainError


class MembershipError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "membership_error"
    default_message = "La operación sobre la membresía no es válida."


class MemberInactive(MembershipError):
    """El socio está dado de baja o inactivo: no se le vende (D21)."""

    status = 422
    code = "member_inactive"
    default_message = "El socio no está activo."


class PlanInvalid(MembershipError):
    """El plan no existe o está dado de baja (`PlanNotFound` de `plans.get`)."""

    status = 422
    code = "plan_invalid"
    default_message = "El plan no es válido."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "plan_id",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class PlanInactive(MembershipError):
    """El plan existe pero no está activo (`is_active = false`)."""

    status = 422
    code = "plan_inactive"
    default_message = "El plan no está activo."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "plan_id",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class StartDateTooRetroactive(MembershipError):
    """`start_date` antes de hoy menos `max_retroactive_days` (N-24)."""

    status = 422
    code = "start_date_too_retroactive"
    default_message = "La fecha de inicio es demasiado antigua."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "start_date",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class StartDateTooFar(MembershipError):
    """`start_date` después de hoy más `MAX_START_AHEAD_DAYS` (M-4, S3-D47)."""

    status = 422
    code = "start_date_too_far"
    default_message = "La fecha de inicio está demasiado lejos."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "start_date",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)


class MembershipConflict(MembershipError):
    """El socio ya tiene una membresía vigente o futura (D8): 409 con `existing_id`."""

    status = 409
    code = "membership_conflict"
    default_message = "El socio ya tiene una membresía vigente o por empezar."


class MembershipOverlap(MembershipError):
    """Las fechas chocan con otra membresía no cancelada del socio (D8; también la `EXCLUDE`)."""

    status = 409
    code = "membership_overlap"
    default_message = "Las fechas se cruzan con otra membresía del socio."


class MembershipNotFound(MembershipError):
    """La membresía no existe."""

    status = 404
    code = "membership_not_found"
    default_message = "No se encontró la membresía."


class FreezeRejected(MembershipError):
    """`rules.FreezeError` convertido en error de dominio (S3-B2, D14): lleva el `code`, el
    `field` y el `status` de la regla que falló. 422 para la entrada mal formada
    (`validation_error` con `field="frozen_to"`, `freeze_too_retroactive`,
    `freeze_outside_validity`); 409 para lo que depende del estado de la membresía
    (`membership_not_freezable`, `freeze_already_scheduled`, `freeze_limit_reached`,
    `freeze_days_exceeded`)."""

    status = 409
    code = "freeze_rejected"
    default_message = "No se puede congelar la membresía."


class OverlapsFutureMembership(MembershipError):
    """El fin corrido por la congelación choca con otra membresía no cancelada del socio (D14):
    409 con `existing_id` si lo da la revisión previa; sin él si sale de la `EXCLUDE`."""

    status = 409
    code = "overlaps_future_membership"
    default_message = "La congelación haría chocar la membresía con otra del socio."


class FutureMembershipExists(MembershipError):
    """Renovar (S3-B6, Q1, D8) con una futura ya creada (`pending_payment` de cualquier fecha, o
    `active`/`expiring` que aún no empieza): 409 con el `existing_id` de esa futura."""

    status = 409
    code = "future_membership_exists"
    default_message = "El socio ya tiene una renovación por empezar."


class MembershipAlreadyCancelled(MembershipError):
    """La membresía ya estaba anulada (S3-B6, US-090): una anulada es terminal (S3-D48)."""

    status = 409
    code = "membership_already_cancelled"
    default_message = "La membresía ya está anulada."


class CancelReasonInvalid(MembershipError):
    """Motivo de anulación vacío, invisible, con caracteres de control, de menos de 5 o de más de
    500 caracteres tras recortar (S3-B6, D17, M-7): 422 `validation_error` con `field="reason"`,
    el mismo código que dan los 422 de forma del esquema."""

    status = 422
    code = "validation_error"
    default_message = "El motivo de la anulación no es válido."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = "reason",
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(code, message, field=field, existing_id=existing_id, status=status)
