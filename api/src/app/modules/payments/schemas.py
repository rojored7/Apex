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
- `VoidPaymentIn(reason)` (S3-B5, US-097; D17, M-7; `extra="forbid"`): `reason` es `SafeText`
  (NFC, recortado, sin `Cc`/`Cf`, con algo visible: vacío, espacios, NUL y U+200B dan 422
  `validation_error` con `field="reason"`), con un tope previo de `VOID_REASON_INPUT_MAX` (2000)
  caracteres antes de normalizar. El largo (hasta 500 tras recortar) lo decide
  `rules.normalize_void_reason` en `void` con el mismo 422. La respuesta es `PaymentOut`.

S3-B8 (US-098, US-099, US-100; D26, M-8, L-2, S3-D51, S3-D57):
- `PaymentListQuery` (`extra="forbid"`): los filtros de `GET /payments`; `from` es alias de
  `from_`; `from` y `to` con zona; `method` del `Literal`; `voided` y `backdated` tri-estado; `q`
  hasta `MAX_SEARCH_LENGTH`. El rango contra "hoy" (M-4) lo valida `queries.list`.
- `PaymentRow`: la fila de la lista, sin datos cifrados del socio (solo nombre y apellido, en
  claro por regla), con el plan y las fechas de la membresía (`memberships.refs_for`),
  `registered_by_name` como correo parcial (L-2) y `backdated` (M-8).
- `PaymentDetail(PaymentRow)`: más `voided_by`, `voided_by_name` (correo parcial), `voided_at` y
  `created_at`.
- `PaymentsByMethod` y `PaymentsSummary(month, total_cop, by_method, voided_count,
  payments_count)`: el resumen del mes de Bogotá (D23); montos y conteos enteros.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
)

from app.core.pagination import MAX_SEARCH_LENGTH
from app.core.validators import SafeText, check_visible_text
from app.modules.payments.models import MAX_AMOUNT_COP, REFERENCE_MAX_LENGTH
from app.modules.payments.rules import REFERENCE_PATTERN, VOID_REASON_MAX, normalize_reference

VOID_REASON_INPUT_MAX: Final = 4 * VOID_REASON_MAX
"""Tope holgado de entrada del motivo (2000), antes de NFC y recorte (revisión de seguridad de
S3-B5, LOW-2): lo enorme se corta sin trabajo; entre 501 y 2000 decide `normalize_void_reason`."""

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


class VoidPaymentIn(BaseModel):
    """Cuerpo de `POST /payments/{payment_id}/void` (S3-B5)."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[
        str,
        StringConstraints(max_length=VOID_REASON_INPUT_MAX),
        AfterValidator(check_visible_text),
    ]


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


class PaymentListQuery(BaseModel):
    """Filtros de `GET /payments` (S3-B8, D26). `from` llega por alias (`from_` en Python)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    q: str | None = Field(default=None, max_length=MAX_SEARCH_LENGTH)
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    method: PaymentMethod | None = None
    registered_by: UUID | None = None
    voided: bool | None = None
    backdated: bool | None = None
    member_id: UUID | None = None
    membership_id: UUID | None = None


class PaymentRow(BaseModel):
    """Una fila de `GET /payments` (S3-B8, D26, M-8, L-2)."""

    id: UUID
    paid_at: datetime
    amount_cop: int
    method: PaymentMethod
    reference: str | None
    voided: bool
    void_reason: str | None
    registered_by: UUID
    registered_by_name: str | None
    membership_id: UUID
    member_id: UUID
    member_first_name: str
    member_last_name: str
    plan_name: str
    membership_start_date: date
    membership_end_date: date
    backdated: bool


class PaymentDetail(PaymentRow):
    """`GET /payments/{payment_id}` (S3-B8, US-099; L-2)."""

    voided_by: UUID | None
    voided_by_name: str | None
    voided_at: datetime | None
    created_at: datetime


class PaymentsByMethod(BaseModel):
    """Total no anulado por medio; siempre las tres claves (D24)."""

    cash: int
    nequi: int
    breb: int


class PaymentsSummary(BaseModel):
    """`GET /payments/summary` (S3-B8, US-100; D23): el mes `AAAA-MM` de Bogotá."""

    month: str
    total_cop: int
    by_method: PaymentsByMethod
    voided_count: int
    payments_count: int
