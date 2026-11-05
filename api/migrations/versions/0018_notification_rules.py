"""Reglas de aviso (S5-B6, US-121; S5-D24, S5-D25).

Revision ID: 0018_notification_rules
Revises: 0017_notification_templates
Create Date: 2026-11-05

Tabla `notifications.notification_rules`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `name` (`text`), `trigger` (`text`), `offset_days` (`integer`), `channel` (`text`),
  `template_id` (`uuid`, FK a `notifications.notification_templates(id)` `ON DELETE RESTRICT`) e
  `is_active` (`boolean`), todas obligatorias;
- CHECK `ck_notification_rules_name_not_blank`;
- CHECK `ck_notification_rules_trigger`: `trigger IN ('membership_expiring', 'membership_expired')`;
- CHECK `ck_notification_rules_channel`: `channel IN ('email', 'whatsapp_link')`;
- CHECK `ck_notification_rules_offset_days_sign`: un vencimiento por venir lleva desfase `<= 0` y
  uno ya vencido `>= 1` (fecha del aviso = fin de la membresía + desfase);
- único parcial `uq_notification_rules_active_key (trigger, offset_days, channel) WHERE
  is_active`: una sola regla activa por disparador, desfase y canal.
Sin triggers: las reglas se editan y se desactivan, no se borran.

`downgrade`: borra la tabla (el CHECK, el índice y la FK caen con ella) y deja la de plantillas.
Las reglas guardadas SE PIERDEN al bajar: hacer el volcado `antes-0018` primero (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_notification_rules"
down_revision: str | None = "0017_notification_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "notifications"
TABLE: Final = "notification_rules"
ACTIVE_KEY_INDEX: Final = "uq_notification_rules_active_key"


def common_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.notification_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint(
            "trigger IN ('membership_expiring', 'membership_expired')", name="trigger"
        ),
        sa.CheckConstraint("channel IN ('email', 'whatsapp_link')", name="channel"),
        sa.CheckConstraint(
            "(trigger = 'membership_expiring' AND offset_days <= 0) "
            "OR (trigger = 'membership_expired' AND offset_days >= 1)",
            name="offset_days_sign",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        ACTIVE_KEY_INDEX,
        TABLE,
        ["trigger", "offset_days", "channel"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
