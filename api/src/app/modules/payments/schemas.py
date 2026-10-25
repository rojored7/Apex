"""Esquemas de pagos (S3-B3, US-095 y US-056; D4, D17, D24, D25, S3-D41, S3-D50).

- `PaymentMethod`: `Literal` de los tres códigos fijos (D24; los mismos de
  `settings.schemas.PAYMENT_METHOD_CODES` y de `models.PAYMENT_METHODS`).
- `PaymentIn` (`extra="forbid"`; también es el `first_payment` de la venta, D4, desde B4):
  `amount_cop` `StrictInt` de 1 a `MAX_AMOUNT_COP` (ni `"120000"`, ni `120000.5`, ni `true`);
  `method`; `reference` opcional (`SafeText`, recortada, vacía pasa a `None` con
  `rules.normalize_reference`, hasta 64 y con el patrón de comprobante `REFERENCE_PATTERN`, M-7);
  `paid_at` con zona (`AwareDatetime`) u omitido (ahora); `confirm_overpayment` y
  `confirm_duplicate` (`StrictBool`, falsos por defecto; no se guardan, H-1).
- `PaymentOut`: la fila registrada (sin `confirm_*`).
- `PaymentMethodOut(code, label, hint)` y `PaymentMethodsOut(items)`: `GET /payments/methods`
  responde un objeto, no un arreglo (D25, S3-C7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
)

from app.core.validators import SafeText
from app.modules.payments.models import MAX_AMOUNT_COP, REFERENCE_MAX_LENGTH
from app.modules.payments.rules import REFERENCE_PATTERN, normalize_reference

PaymentMethod = Literal["cash", "nequi", "breb"]
Reference = Annotated[
    SafeText, StringConstraints(max_length=REFERENCE_MAX_LENGTH, pattern=REFERENCE_PATTERN)
]


class PaymentIn(BaseModel):
    """Cuerpo de un pago (registrar, B4; primer pago de la venta, D4)."""

    model_config = ConfigDict(extra="forbid")

    amount_cop: Annotated[StrictInt, Field(ge=1, le=MAX_AMOUNT_COP)]
    method: PaymentMethod
    reference: Reference | None = None
    paid_at: AwareDatetime | None = None
    confirm_overpayment: StrictBool = False
    confirm_duplicate: StrictBool = False

    @field_validator("reference", mode="before")
    @classmethod
    def _normalizar_referencia(cls, valor: object) -> object:
        return normalize_reference(valor) if isinstance(valor, str) else valor


class PaymentOut(BaseModel):
    id: UUID
    membership_id: UUID
    member_id: UUID
    amount_cop: int
    method: PaymentMethod
    reference: str | None
    paid_at: datetime
    registered_by: UUID
    voided: bool
    void_reason: str | None
    voided_by: UUID | None
    voided_at: datetime | None
    created_at: datetime


class PaymentMethodOut(BaseModel):
    code: PaymentMethod
    label: str
    hint: str


class PaymentMethodsOut(BaseModel):
    items: list[PaymentMethodOut]
