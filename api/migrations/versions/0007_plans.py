"""Planes (S2-B9, US-078 y US-079; DECISIÓN 32, S2-D26, S2-D32).

Revision ID: 0007_plans
Revises: 0006_members
Create Date: 2026-10-22

Tabla `plans.plans`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at` (borrado lógico);
- `name` (texto no vacío tras `btrim`), `price_cop` (entero en COP), `kind` (`days` o
  `classes`), `duration_days`, `class_count` (nula salvo en `classes`) e `is_active` (default
  `true`); todas no nulas salvo `class_count` y `deleted_at`;
- CHECKs nombrados: `price_cop > 0`, `duration_days > 0`, `kind IN ('days','classes')`, el par
  `kind`/`class_count` y el nombre no vacío. El par lleva `class_count IS NOT NULL` explícito:
  el texto del blueprint (`kind = 'classes' AND class_count > 0`) da NULL con `class_count`
  nulo y un CHECK con NULL acepta la fila (corregido en B9, ver DECISIONES S2-B9);
- `uq_plans_name_alive`: único sobre `lower(btrim(name))` entre los vivos (DECISIÓN 32): "Mensual"
  y "mensual" chocan; un plan dado de baja libera su nombre;
- `ix_plans_active_alive (is_active) WHERE deleted_at IS NULL` (la lista del coach, S2-D26).
El esquema `plans` lo crea 0001; aquí no se crea ni se borra. `downgrade` borra la tabla.
`common_columns()` se declara dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_plans"
down_revision: str | None = "0006_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "plans"
TABLE = "plans"


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
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_cop", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("class_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("price_cop > 0", name="price_cop_positive"),
        sa.CheckConstraint("duration_days > 0", name="duration_days_positive"),
        sa.CheckConstraint("kind IN ('days', 'classes')", name="kind"),
        sa.CheckConstraint(
            "(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0)"
            " OR (kind = 'days' AND class_count IS NULL)",
            name="class_count_by_kind",
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_plans_name_alive",
        TABLE,
        [sa.text("lower(btrim(name))")],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_plans_active_alive",
        TABLE,
        ["is_active"],
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
