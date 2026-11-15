"""Contrato HTTP del tablero (S4A-B8; US-108, US-110; S4A-D27, S4A-D28).

- `MovementOut`: una frase de "últimos movimientos" (`seq`, `at`, `phrase`, `table_name` de las
  tres tablas reales de negocio, `record_id` y `member_id`); nunca `before`/`after` ni valores.
- `DashboardOut`: `today` (Bogotá), los cinco conteos del resumen de membresías, `income_month`
  (`AAAA-MM`), `income_month_cop` (`null` para el coach, S4A-D118), `last_movements` (máximo
  `LAST_MOVEMENTS_LIMIT`; sin montos para el coach), `notifications_today` y
  `members_without_consent` (enteros desde S5-B10, US-132; S5-D39, S5-D80), `attendance_week`
  (`AttendanceWeekOut`) y `sessions_today` (lista de `SessionTodayOut`, `[]` sin clases, maximo
  `SESSIONS_TODAY_LIMIT`), obligatorios y no nulos desde S7-R3 (US-164, S7-D16: cambio de tipo,
  antes `null`), y `wod_today`, siempre presente y `null` hasta v0.5 (nunca `exclude_none`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LAST_MOVEMENTS_LIMIT: Final = 10
"""Frases de `last_movements` (US-110; el límite se aplica después de excluir al sistema)."""
SESSIONS_TODAY_LIMIT: Final = 50
"""Sesiones de hoy del tablero (US-164; igual a `classes.TODAY_SESSIONS_LIMIT`)."""
MONTH_PATTERN: Final = r"^\d{4}-(0[1-9]|1[0-2])$"

INCOME_MONTH_COP_DESCRIPTION: Final = (
    "Ingresos del mes en COP (pagos no anulados). null para el coach: solo el admin ve "
    "ingresos y montos (S4A-D118)."
)

SessionStatus = Literal["scheduled", "done", "cancelled"]
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


class AttendanceWeekOut(BaseModel):
    """Asistencias vivas de lunes 00:00 (Bogotá) a ahora y las que llevan bandera (US-164)."""

    model_config = ConfigDict(extra="forbid")

    count: int
    flagged_count: int


class SessionTodayOut(BaseModel):
    """Una sesión de hoy (Bogotá) con su ocupación (US-164); `status` es el calculado."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    starts_at: datetime
    duration_min: int
    coach_name: str | None
    capacity: int
    attendance_count: int
    status: SessionStatus


class DashboardOut(BaseModel):
    """`GET /dashboard` (US-108, US-164; S4A-D27, S7-D16): KPI de v0.1, de avisos y de clases;
    solo `wod_today` sigue en `null` hasta v0.5."""

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
    notifications_today: int
    members_without_consent: int
    attendance_week: AttendanceWeekOut
    sessions_today: list[SessionTodayOut] = Field(max_length=SESSIONS_TODAY_LIMIT)
    wod_today: str | None = None
