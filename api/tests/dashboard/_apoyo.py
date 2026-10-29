"""Apoyo de las pruebas del tablero (plan del Sprint 4A, sección 2, bloque B8).

- `DASHBOARD = "/api/v1/dashboard"`.
- `CAMPOS_DASHBOARD`: las claves exactas de `DashboardOut` (S4A-D27), con los cinco campos
  futuros (`FUTUROS`), que siempre están presentes y en `null`.
- `CAMPOS_MOVEMENT`: las claves exactas de `MovementOut` (S4A-D28).
"""

from __future__ import annotations

from typing import Final

DASHBOARD: Final = "/api/v1/dashboard"
FUTUROS: Final = frozenset(
    {
        "notifications_today",
        "members_without_consent",
        "attendance_week",
        "sessions_today",
        "wod_today",
    }
)
CAMPOS_DASHBOARD: Final = (
    frozenset(
        {
            "today",
            "members_active",
            "members_expiring",
            "members_expired",
            "members_frozen",
            "members_pending_payment",
            "income_month",
            "income_month_cop",
            "last_movements",
        }
    )
    | FUTUROS
)
CAMPOS_MOVEMENT: Final = frozenset({"seq", "at", "phrase", "table_name", "record_id", "member_id"})
