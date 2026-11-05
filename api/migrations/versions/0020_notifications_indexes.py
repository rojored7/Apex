"""Índices de la revisión final de base de datos (S5-V8, S5-D255).

Revision ID: 0020_notifications_indexes
Revises: 0019_notifications
Create Date: 2026-11-05

Tres índices no únicos:
- `ix_notifications_membership_id` en `notifications.notifications (membership_id)`: lo usa
  `_existing` de `generate.py` por trozos de membresías; sin él, un Seq Scan por trozo;
- `ix_members_created_at_id` en `members.members (created_at, id)` y
  `ix_payments_paid_at_id` en `payments.payments (paid_at, id)`: paginación por llave de las
  exportaciones CSV (S5-D246).

`downgrade`: borra los tres índices y no toca datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0020_notifications_indexes"
down_revision: str | None = "0019_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre, tabla, esquema, columnas)
INDICES: Final[tuple[tuple[str, str, str, tuple[str, ...]], ...]] = (
    ("ix_notifications_membership_id", "notifications", "notifications", ("membership_id",)),
    ("ix_members_created_at_id", "members", "members", ("created_at", "id")),
    ("ix_payments_paid_at_id", "payments", "payments", ("paid_at", "id")),
)


def upgrade() -> None:
    for nombre, tabla, esquema, columnas in INDICES:
        op.create_index(nombre, tabla, list(columnas), schema=esquema)


def downgrade() -> None:
    for nombre, tabla, esquema, _columnas in reversed(INDICES):
        op.drop_index(nombre, table_name=tabla, schema=esquema)
