"""Preferencias de canal de aviso por socio (S5-B5, US-123; S5-D31, S5-D34).

Revision ID: 0016_member_channel_preferences
Revises: 0015_crypto_provider_migration
Create Date: 2026-11-05

Tabla `members.member_channel_preferences` (una fila por socio y canal que el socio o el staff
fijó de forma explícita; sin fila rige el valor por defecto de `members/rules.effective_channels`):
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `member_id` con FK a
  `members.members(id)` `ON DELETE RESTRICT` (el borrado de socios es lógico), `channel` (`text`)
  y `active` (`boolean`), todas obligatorias;
- CHECK `ck_member_channel_preferences_channel`: `channel IN ('email', 'whatsapp_link')`;
- único `uq_member_channel_preferences_member_id_channel (member_id, channel)`.
Sin triggers: la tabla es de datos vivos (se actualiza con upsert), no append-only.

`downgrade`: borra la tabla (el CHECK, el único y la FK caen con ella). No toca `members.members`.
Las preferencias de canal guardadas SE PIERDEN al bajar (el opt-in de correo vuelve al valor por
defecto, apagado): hacer el volcado `antes-0016` primero (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_member_channel_preferences"
down_revision: str | None = "0015_crypto_provider_migration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "members"
TABLE: Final = "member_channel_preferences"
UNIQUE_NAME: Final = "uq_member_channel_preferences_member_id_channel"


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
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("channel IN ('email', 'whatsapp_link')", name="channel"),
        sa.UniqueConstraint("member_id", "channel", name=UNIQUE_NAME),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
