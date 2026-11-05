"""Avisos (S5-B7, US-124, US-127 a US-130; S5-D24, RN-17, N-37).

Revision ID: 0019_notifications
Revises: 0018_notification_rules
Create Date: 2026-11-05

Tabla `notifications.notifications` (un aviso por regla, membresía y fecha objetivo):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `rule_id` (`uuid`, FK a `notifications.notification_rules(id)` `ON DELETE RESTRICT`),
  `member_id` y `membership_id` (`uuid`, sin FK: no hay joins entre esquemas, N-37),
  `target_date` (`date`), `channel`, `status`, `rendered_subject`, `rendered_body` (`text`),
  `attempts` (`integer`, por defecto 0), todas obligatorias;
- `last_error`, `sent_at`, `sent_by` y `skip_reason`, opcionales;
- CHECK `ck_notifications_channel` (`email`, `whatsapp_link`), `ck_notifications_status`
  (`pending`, `sent`, `failed`, `skipped`), `ck_notifications_attempts` (`attempts >= 0`),
  `ck_notifications_skip_reason` (`status <> 'skipped' OR skip_reason IS NOT NULL`) y
  `ck_notifications_last_error` (conjunto cerrado de códigos de S5-D24);
- único `uq_notifications_rule_membership_target (rule_id, membership_id, target_date)` (RN-17);
- índices `ix_notifications_status_target_date (status, target_date)` (la lista de hoy) y
  `ix_notifications_member_target_date (member_id, target_date DESC)` (la pestaña del socio).
Sin triggers: los avisos se envían y se omiten, no se borran (RN-14).

`downgrade`: borra la tabla (CHECK, índices y FK caen con ella) y deja plantillas y reglas.
Los avisos guardados SE PIERDEN al bajar: hacer el volcado `antes-0019` primero (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_notifications"
down_revision: str | None = "0018_notification_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "notifications"
TABLE: Final = "notifications"
UNIQUE_KEY: Final = "uq_notifications_rule_membership_target"
STATUS_INDEX: Final = "ix_notifications_status_target_date"
MEMBER_INDEX: Final = "ix_notifications_member_target_date"


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
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.notification_rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rendered_subject", sa.Text(), nullable=False),
        sa.Column("rendered_body", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sent_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("channel IN ('email', 'whatsapp_link')", name="channel"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped')", name="status"),
        sa.CheckConstraint("attempts >= 0", name="attempts"),
        sa.CheckConstraint("status <> 'skipped' OR skip_reason IS NOT NULL", name="skip_reason"),
        sa.CheckConstraint(
            "last_error IS NULL OR last_error IN "
            "('timeout', 'auth', 'refused', 'invalid_recipient', 'unknown')",
            name="last_error",
        ),
        sa.UniqueConstraint("rule_id", "membership_id", "target_date", name=UNIQUE_KEY),
        schema=SCHEMA,
    )
    op.create_index(STATUS_INDEX, TABLE, ["status", "target_date"], schema=SCHEMA)
    op.create_index(
        MEMBER_INDEX,
        TABLE,
        ["member_id", sa.text("target_date DESC")],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
