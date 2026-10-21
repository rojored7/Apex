"""Esquemas de v0.1 y extensión btree_gist.

Revision ID: 0001_core_schemas
Revises:
Create Date: 2026-10-21

Un esquema por módulo (CLAUDE.md). `btree_gist` sostiene el `EXCLUDE USING gist`
de membresías (Q1). El downgrade usa `RESTRICT`, nunca `CASCADE`: si un esquema
tiene tablas, falla a propósito en vez de borrar datos.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_core_schemas"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = (
    "audit",
    "crypto",
    "auth",
    "settings",
    "members",
    "plans",
    "memberships",
    "payments",
    "worker",
)


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" RESTRICT')
