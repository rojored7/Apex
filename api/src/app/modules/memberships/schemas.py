"""Esquemas de membresías (S3-B1, US-084; D4, D16).

- `SellMembershipIn`: `plan_id`, `start_date` opcional (hoy si falta; con `renew` se descarta),
  `renew` (`StrictBool`; S3-B6 quita el validador provisional de B1 que respondía 422) y
  `first_payment` opcional, que desde B4 es `payments.schemas.PaymentIn` (D4: una sola fuente
  de validadores; el 422 de forma sale con `field="first_payment.<campo>"`).
  `extra="forbid"`: el cliente nunca fija `agreed_price_cop` (D16).
- `MembershipOut` y `SellMembershipOut` (`first_payment_id`: el pago registrado con la venta, o
  nulo).
- `FreezeIn` (S3-B2: `frozen_from` y `frozen_to`, `extra="forbid"`) y `FreezeOut` (`id`,
  `frozen_from`, `frozen_to`, `days`, `created_at`).
- `CancelMembershipIn(reason)` (S3-B6, US-090; D17, M-7; `extra="forbid"`): `reason` es
  `SafeText` (NFC, recortado, sin `Cc`/`Cf`, con algo visible) con un tope previo holgado de
  `CANCEL_REASON_INPUT_MAX` (2000) caracteres antes de normalizar (como S3-D83); el largo de 5 a
  500 tras recortar lo decide `rules.normalize_cancel_reason` en `cancel`, con el mismo 422
  `validation_error` en `reason`. La respuesta es `MembershipOut`.
- `RenewalPreviewOut(start_date, end_date, agreed_price_cop, current_end_date)` (S3-B6, US-088):
  lo que crearía la renovación; `current_end_date` es el fin de la vigente (con la extensión por
  congelación) o nulo si no hay.
- Contratos para otros módulos (dataclasses, nunca el ORM): `MembershipRef` (lo que `refs_for`
  devuelve por id de membresía) y `PaymentTarget` (lo que lee el gate de pagos, B4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool, StringConstraints

from app.core.validators import check_visible_text
from app.modules.memberships.rules import CANCEL_REASON_MAX
from app.modules.payments.schemas import PaymentIn


class SellMembershipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    start_date: date | None = None
    renew: StrictBool = False
    first_payment: PaymentIn | None = None


CANCEL_REASON_INPUT_MAX: Final = 4 * CANCEL_REASON_MAX
"""Tope holgado de entrada del motivo de anulación (2000), antes de NFC y recorte (S3-D83)."""


class CancelMembershipIn(BaseModel):
    """Cuerpo de `POST /memberships/{membership_id}/cancel` (S3-B6)."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[
        str,
        StringConstraints(max_length=CANCEL_REASON_INPUT_MAX),
        AfterValidator(check_visible_text),
    ]


class RenewalPreviewOut(BaseModel):
    """Vista previa de la renovación (S3-B6): lo mismo que `sell(..., renew=True)` crearía."""

    start_date: date
    end_date: date
    agreed_price_cop: int
    current_end_date: date | None


class FreezeIn(BaseModel):
    """Cuerpo de `POST /memberships/{membership_id}/freeze` (S3-B2, D14). Sin `reason`: la tabla
    no tiene motivo (el modal del diseño lo pinta; el front lo omite con `// DESIGN-GAP:`). Las
    fechas invertidas no se rechazan aquí: las valida `rules.apply_freeze` después del estado
    (422 `validation_error` con `field="frozen_to"`)."""

    model_config = ConfigDict(extra="forbid")

    frozen_from: date
    frozen_to: date


class FreezeOut(BaseModel):
    """Una congelación de la membresía (S3-B2, D14)."""

    id: UUID
    frozen_from: date
    frozen_to: date
    days: int
    created_at: datetime


class MembershipOut(BaseModel):
    id: UUID
    member_id: UUID
    member_name: str
    plan_id: UUID
    plan_name: str
    agreed_price_cop: int
    paid_cop: int
    start_date: date
    end_date: date
    classes_total: int | None
    classes_remaining: int | None
    status: str
    freezes: list[FreezeOut]
    cancel_reason: str | None
    cancelled_at: datetime | None
    created_at: datetime


class SellMembershipOut(MembershipOut):
    first_payment_id: UUID | None


@dataclass(frozen=True, slots=True)
class MembershipRef:
    """Nombre del socio, plan y fechas de una membresía (contrato de `refs_for`; D26)."""

    member_id: UUID
    member_first_name: str
    member_last_name: str
    plan_name: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class PaymentTarget:
    """Lo que el gate de pagos sabe de la membresía, leída con `FOR UPDATE` (D1, B4)."""

    exists: bool
    cancelled: bool
    member_id: UUID | None
