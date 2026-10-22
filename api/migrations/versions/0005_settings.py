"""Configuración del gimnasio por secciones con versión optimista (US-054 T1; N-17).

Revision ID: 0005_settings
Revises: 0004_auth
Create Date: 2026-10-22

- `settings.settings_sections`: una fila por sección guardada al menos una vez; `value` JSONB
  validado por el esquema de la sección en `settings.schemas`; `version` arranca en 0 (sin
  fila) y sube de a uno en cada guardado; `updated_by` sin FK (S7: el módulo no se acopla a
  `auth`).
- `CHECK key_valid` con las 8 claves del catálogo (las no habilitadas responden 404 en el api)
  y `CHECK version_non_negative`; índice único `uq_settings_sections_key`, que también
  resuelve dos primeros guardados concurrentes (el segundo recibe 409).
- Sin filas sembradas: los valores por defecto viven en `SECTION_DEFAULTS`.
El esquema `settings` lo crea 0001; aquí no se crea ni se borra. `common_columns()` se declara
dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_settings"
down_revision: str | None = "0004_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "settings_sections",
        *common_columns(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "key IN ('gym', 'hours', 'payment_methods', 'channels', 'classes', "
            "'memberships', 'tv', 'privacy')",
            name="key_valid",
        ),
        sa.CheckConstraint("version >= 0", name="version_non_negative"),
        schema="settings",
    )
    op.create_index(
        "uq_settings_sections_key", "settings_sections", ["key"], unique=True, schema="settings"
    )


def downgrade() -> None:
    op.drop_table("settings_sections", schema="settings")
