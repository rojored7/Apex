"""Esquemas de membresías (S3-B1, US-084; D4, D16).

- `SellMembershipIn`: `plan_id`, `start_date` opcional (hoy si falta), `renew` (`StrictBool`, B6)
  y `first_payment`, que en B1 solo admite nulo (B4 lo abre a `payments.schemas.PaymentIn`, así B1
  no importa `payments`). `extra="forbid"`: el cliente nunca fija `agreed_price_cop` (D16).
- `MembershipOut` y `SellMembershipOut` (`first_payment_id`, nulo hasta B4).
- Contratos para otros módulos (dataclasses, nunca el ORM): `MembershipRef` (lo que `refs_for`
  devuelve por id de membresía) y `PaymentTarget` (lo que lee el gate de pagos, B4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator


class SellMembershipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    start_date: date | None = None
    renew: StrictBool = False
    first_payment: None = None

    @field_validator("renew")
    @classmethod
    def _renovar_llega_en_b6(cls, valor: bool) -> bool:
        """Hasta S3-B6 solo `false` (revisión de seguridad de B1, M1): `true` daría 500 por el
        `NotImplementedError` del service. Es un 422 de forma con `field="renew"`; el contrato
        sigue declarando `renew` booleano y B6 quita este validador."""
        if valor:
            raise ValueError("renew todavía no está disponible")
        return valor


class FreezeOut(BaseModel):
    frozen_from: date
    frozen_to: date
    days: int


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
