"""Resultados de los WODs y el esquema `results` (S8-B1, US-169; S8-D10, S8-D35, S8-D41).

Revision ID: 0036_results_wod_results
Revises: 0035_wods_wod_movements
Create Date: 2026-11-15

Esquema `results` y tabla `results.wod_results`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `wod_id`, `member_id` y `session_id` (NULL) sin FK entre esquemas; `wod_date` y `benchmark_id`
  copiados del WOD al insertar; `level` (`rx|rx_plus|scaled`); `seconds` (1 a 86.400), `rounds`
  (0 a 1.000), `reps` (0 a 100.000) y `load_g` (gramos enteros, 0 a 1.000.000; S8-D41);
  `capped` (solo con `seconds` y `reps`, N-43); `scaled_movement_ids uuid[]` (L-2: ids del
  WOD, hasta 30, solo con `scaled`); `status` (`validated|pending`); `recorded_by`, `validated_by`,
  `validated_at`; `supersedes_id`; `is_current`; `source` (`desk|kiosk`, M-1);
- M-5: `CHECK ((status = 'validated') = (validated_by IS NOT NULL AND validated_at IS NOT NULL))`,
  `CHECK (supersedes_id <> id)`, `UNIQUE (id, wod_id, member_id)` y FK compuesta
  `(supersedes_id, wod_id, member_id)` hacia esa clave (una corrección es del mismo socio y WOD);
- índices: único parcial `(wod_id, member_id) WHERE is_current`, `(wod_id, status) WHERE
  is_current`, único parcial `(supersedes_id)` (un resultado se corrige una sola vez) y
  `(member_id, wod_date DESC) WHERE is_current`.
La auditoría la hace el hook del ORM (`__audited__`). Las guardas de inmutabilidad llegan en `0037`.

`downgrade`: índices, tabla y esquema. Los resultados guardados SE PIERDEN al bajar; el volcado
previo es `sprint-08-antes-0036.dump` (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_results_wod_results"
down_revision: str | None = "0035_wods_wod_movements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "results"
TABLE: Final = "wod_results"
UQ_CURRENT: Final = "uq_wod_results_current"
IX_LEADERBOARD: Final = "ix_wod_results_leaderboard"
UQ_SUPERSEDES: Final = "uq_wod_results_supersedes"
IX_MEMBER: Final = "ix_wod_results_member_date"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("level", "level IN ('rx', 'rx_plus', 'scaled')"),
    ("status", "status IN ('validated', 'pending')"),
    ("source", "source IN ('desk', 'kiosk')"),
    ("seconds", "seconds IS NULL OR seconds BETWEEN 1 AND 86400"),
    ("rounds", "rounds IS NULL OR rounds BETWEEN 0 AND 1000"),
    ("reps", "reps IS NULL OR reps BETWEEN 0 AND 100000"),
    ("load_g", "load_g IS NULL OR load_g BETWEEN 0 AND 1000000"),
    ("capped_shape", "NOT capped OR (seconds IS NOT NULL AND reps IS NOT NULL)"),
    (
        "validated_pair",
        "(status = 'validated') = (validated_by IS NOT NULL AND validated_at IS NOT NULL)",
    ),
    ("supersedes_not_self", "supersedes_id <> id"),
    ("scaled_ids_max", "cardinality(scaled_movement_ids) <= 30"),
    ("scaled_ids_level", "scaled_movement_ids = '{}' OR level = 'scaled'"),
)


def common_columns() -> list[sa.Column[object]]:
    """Se declara dentro del archivo porque Alembic carga cada revisión por ruta."""
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
    op.execute("CREATE SCHEMA IF NOT EXISTS results")
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("wod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wod_date", sa.Date(), nullable=False),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("load_g", sa.Integer(), nullable=True),
        sa.Column("capped", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "scaled_movement_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("validated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("validated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("'desk'"), nullable=False),
        sa.UniqueConstraint("id", "wod_id", "member_id", name="uq_wod_results_id_wod_member"),
        sa.ForeignKeyConstraint(
            ["supersedes_id", "wod_id", "member_id"],
            [
                "results.wod_results.id",
                "results.wod_results.wod_id",
                "results.wod_results.member_id",
            ],
            name="fk_wod_results_supersedes",
        ),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(
        UQ_CURRENT,
        TABLE,
        ["wod_id", "member_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        IX_LEADERBOARD,
        TABLE,
        ["wod_id", "status"],
        schema=SCHEMA,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        UQ_SUPERSEDES,
        TABLE,
        ["supersedes_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
    )
    op.create_index(
        IX_MEMBER,
        TABLE,
        ["member_id", sa.text("wod_date DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(IX_MEMBER, table_name=TABLE, schema=SCHEMA)
    op.drop_index(UQ_SUPERSEDES, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_LEADERBOARD, table_name=TABLE, schema=SCHEMA)
    op.drop_index(UQ_CURRENT, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute("DROP SCHEMA IF EXISTS results RESTRICT")
