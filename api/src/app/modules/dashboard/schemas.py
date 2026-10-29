"""Contrato HTTP del tablero (S4A-B8; US-108, US-110; S4A-D27, S4A-D28).

- `MovementOut`: una frase de "últimos movimientos" (`seq`, `at`, `phrase`, `table_name` de las
  tres tablas reales de negocio, `record_id` y `member_id`); nunca `before`/`after` ni valores.
- `DashboardOut`: `today` (Bogotá), los cinco conteos del resumen de membresías, `income_month`
  (`AAAA-MM`), `income_month_cop` (`null` para el coach, S4A-D118), `last_movements` (máximo
  `LAST_MOVEMENTS_LIMIT`; sin montos para el coach) y los cinco campos futuros
  `notifications_today`, `members_without_consent`, `attendance_week`,
  `sessions_today` y `wod_today`, siempre presentes y `null` en v0.1 (el front los pinta
  "Disponible en v0.x"; nunca `exclude_none`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LAST_MOVEMENTS_LIMIT: Final = 10
"""Frases de `last_movements` (US-110; el límite se aplica después de excluir al sistema)."""
MONTH_PATTERN: Final = r"^\d{4}-(0[1-9]|1[0-2])$"

INCOME_MONTH_COP_DESCRIPTION: Final = (
    "Ingresos del mes en COP (pagos no anulados). null para el coach: solo el admin ve "
    "ingresos y montos (S4A-D118)."
)

MovementTable = Literal["members.members", "memberships.memberships", "payments.payments"]


class MovementOut(BaseModel):
    """Una frase de los últimos movimientos (S4A-D28)."""

    model_config = ConfigDict(extra="forbid")

    seq: int
    at: datetime
    phrase: str
    table_name: MovementTable
    record_id: UUID | None
    member_id: UUID | None


class DashboardOut(BaseModel):
    """`GET /dashboard` (US-108; S4A-D27): KPI de v0.1 y los cinco futuros en `null`."""

    model_config = ConfigDict(extra="forbid")

    today: date
    members_active: int
    members_expiring: int
    members_expired: int
    members_frozen: int
    members_pending_payment: int
    income_month: str = Field(pattern=MONTH_PATTERN)
    income_month_cop: int | None = Field(description=INCOME_MONTH_COP_DESCRIPTION)
    last_movements: list[MovementOut] = Field(max_length=LAST_MOVEMENTS_LIMIT)
    notifications_today: int | None = None
    members_without_consent: int | None = None
    attendance_week: int | None = None
    sessions_today: int | None = None
    wod_today: str | None = None
