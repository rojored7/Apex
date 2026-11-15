"""Catálogo de benchmarks de `wods` (S8-A2, US-166, N-46; S8-D6).

Revision ID: 0033_wods_benchmarks
Revises: 0032_wods_movements
Create Date: 2026-11-15

Tabla `wods.benchmarks`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `name` (1 a 60), `name_norm` (1 a 60; la misma normalización que los movimientos, la calcula
  `modules/wods/rules.py`), `description` (0 a 2.000; vacía por defecto) y `score_type`
  (`time|rounds_reps|reps|load`);
- CHECK `ck_benchmarks_score_type`, `_name_length`, `_name_norm_length` y `_description_length`;
- índice único `uq_benchmarks_name_norm (name_norm)`: la carrera de dos altas (y el
  `ON CONFLICT (name_norm) DO NOTHING` de `seed-benchmarks`) la decide la base;
- triggers `benchmarks_forbid_delete` y `benchmarks_forbid_truncate` (`ENABLE ALWAYS`,
  `tgenabled = 'A'`) sobre `wods.forbid_mutation()`, la función que creó `0032` (solo `0032` la
  crea y solo `0032` la borra): los benchmarks no se borran (RN-14). La auditoría de la tabla la
  hace el hook del ORM (`__audited__`) y, en la siembra, `seed.py` de forma explícita.
Sin FK ni cruce con otros esquemas (N-37): A3 hace que `wods.wods.benchmark_id` apunte aquí.

`downgrade`: triggers, índice y tabla. Los benchmarks guardados SE PIERDEN al bajar; se vuelven a
sembrar con `seed-benchmarks`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_wods_benchmarks"
down_revision: str | None = "0032_wods_movements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "wods"
TABLE: Final = "benchmarks"
UQ_NAME_NORM: Final = "uq_benchmarks_name_norm"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("score_type", "score_type IN ('time', 'rounds_reps', 'reps', 'load')"),
    ("name_length", "char_length(name) BETWEEN 1 AND 60"),
    ("name_norm_length", "char_length(name_norm) BETWEEN 1 AND 60"),
    ("description_length", "char_length(description) <= 2000"),
)

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER benchmarks_forbid_delete BEFORE DELETE ON wods.benchmarks "
    "FOR EACH ROW EXECUTE FUNCTION wods.forbid_mutation()",
    "CREATE TRIGGER benchmarks_forbid_truncate BEFORE TRUNCATE ON wods.benchmarks "
    "FOR EACH STATEMENT EXECUTE FUNCTION wods.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE wods.benchmarks ENABLE ALWAYS TRIGGER benchmarks_forbid_delete",
    "ALTER TABLE wods.benchmarks ENABLE ALWAYS TRIGGER benchmarks_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS benchmarks_forbid_truncate ON wods.benchmarks",
    "DROP TRIGGER IF EXISTS benchmarks_forbid_delete ON wods.benchmarks",
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
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("score_type", sa.Text(), nullable=False),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(UQ_NAME_NORM, TABLE, ["name_norm"], unique=True, schema=SCHEMA)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.drop_index(UQ_NAME_NORM, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
