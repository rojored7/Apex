"""Columnas comunes para las migraciones (US-012, T5).

Cada migración de módulo declara las columnas igual que `CommonColumnsMixin` y
`SoftDeleteMixin` de `app/core/db.py`: `id` UUID, `created_at`, `updated_at`
TIMESTAMPTZ con `now()`, `created_by` UUID NOT NULL, y `deleted_at` opcional.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


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


def soft_delete_column() -> sa.Column[object]:
    return sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True)
