"""Plantillas de aviso y el esquema `notifications` (S5-B6, US-120; S5-D24, S5-D25).

Revision ID: 0017_notification_templates
Revises: 0016_member_channel_preferences
Create Date: 2026-11-05

Crea el esquema `notifications` (el único nuevo del Sprint 5; lo agrega `core/db.APP_SCHEMAS`) y la
tabla `notifications.notification_templates`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `name`, `subject` y `body` (`text`, obligatorias);
- CHECK `ck_notification_templates_name_not_blank`, `..._subject_not_blank` y
  `..._body_not_blank`: ninguno de los tres es solo espacios;
- único `uq_notification_templates_name (name)`.
Sin `deleted_at`: las plantillas no se borran (RN-14) y no tienen triggers.

`downgrade`: borra la tabla y el esquema (`RESTRICT`: falla si otra migración dejó algo dentro).
Las plantillas guardadas SE PIERDEN al bajar: hacer el volcado `antes-0017` primero (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_notification_templates"
down_revision: str | None = "0016_member_channel_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "notifications"
TABLE: Final = "notification_templates"
UNIQUE_NAME: Final = "uq_notification_templates_name"


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
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        sa.CheckConstraint("btrim(subject) <> ''", name="subject_not_blank"),
        sa.CheckConstraint("btrim(body) <> ''", name="body_not_blank"),
        sa.UniqueConstraint("name", name=UNIQUE_NAME),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" RESTRICT')
