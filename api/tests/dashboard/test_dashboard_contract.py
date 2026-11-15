"""Contrato de `GET /dashboard` (S7-R3, US-164 criterio 3). Rojo R3.

Foto de `DashboardOut` del `openapi.json` del Sprint 6: salvo `attendance_week` y `sessions_today`
(que pasan de `integer|null` a objeto y lista, obligatorios), nada cambia. S8-B5 (US-174 CA2,
S8-D16): `wod_today` pasa de `string|null` a `WodTodayOut|null` y es lo unico que cambia desde
entonces.
"""

from __future__ import annotations

from typing import Any, Final

from app.core.config import Settings
from app.main import create_app

ANTERIOR: Final[dict[str, Any]] = {
    "income_month": {
        "pattern": "^\\d{4}-(0[1-9]|1[0-2])$",
        "title": "Income Month",
        "type": "string",
    },
    "income_month_cop": {
        "anyOf": [{"type": "integer"}, {"type": "null"}],
        "description": "Ingresos del mes en COP (pagos no anulados). null para el coach: solo el "
        "admin ve ingresos y montos (S4A-D118).",
        "title": "Income Month Cop",
    },
    "last_movements": {
        "items": {"$ref": "#/components/schemas/MovementOut"},
        "maxItems": 10,
        "title": "Last Movements",
        "type": "array",
    },
    "members_active": {"title": "Members Active", "type": "integer"},
    "members_expired": {"title": "Members Expired", "type": "integer"},
    "members_expiring": {"title": "Members Expiring", "type": "integer"},
    "members_frozen": {"title": "Members Frozen", "type": "integer"},
    "members_pending_payment": {"title": "Members Pending Payment", "type": "integer"},
    "members_without_consent": {"title": "Members Without Consent", "type": "integer"},
    "notifications_today": {"title": "Notifications Today", "type": "integer"},
    "today": {"format": "date", "title": "Today", "type": "string"},
}
CAMBIAN: Final = {"attendance_week", "sessions_today", "wod_today"}


def test_solo_cambia_wod_today(settings_prueba: Settings) -> None:
    abierto = create_app(settings_prueba, run_migrations_on_startup=False).openapi()["components"][
        "schemas"
    ]
    esquema = abierto["DashboardOut"]
    props = esquema["properties"]
    assert set(props) == set(ANTERIOR) | CAMBIAN
    for nombre, anterior in ANTERIOR.items():
        assert props[nombre] == anterior, nombre
    assert props["attendance_week"] == {"$ref": "#/components/schemas/AttendanceWeekOut"}
    assert props["sessions_today"]["type"] == "array"
    assert props["sessions_today"]["maxItems"] == 50
    assert props["sessions_today"]["items"] == {"$ref": "#/components/schemas/SessionTodayOut"}
    assert {"attendance_week", "sessions_today"} <= set(esquema["required"])
    assert "wod_today" not in esquema["required"]
    assert props["wod_today"] == {
        "anyOf": [{"$ref": "#/components/schemas/WodTodayOut"}, {"type": "null"}],
    }
    assert set(abierto["WodTodayOut"]["properties"]) == {
        "id",
        "title",
        "score_type",
        "is_benchmark",
    }
    assert abierto["WodTodayOut"]["additionalProperties"] is False
    assert set(abierto["AttendanceWeekOut"]["properties"]) == {"count", "flagged_count"}
    assert set(abierto["SessionTodayOut"]["properties"]) == {
        "id",
        "starts_at",
        "duration_min",
        "coach_name",
        "capacity",
        "attendance_count",
        "status",
    }
