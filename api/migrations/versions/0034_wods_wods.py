"""WODs de `wods` (S8-A3, US-166, US-167; S8-D7).

Revision ID: 0034_wods_wods
Revises: 0033_wods_benchmarks
Create Date: 2026-11-15

Tabla `wods.wods` (un WOD principal por día):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `date` (fecha civil, única: `uq_wods_date`), `title` (1 a 80), `score_type`
  (`time|rounds_reps|reps|load|none`; `none` es «Sin puntaje»: no admite resultados),
  `time_cap_s` (NULL o 1 a 14.400, solo con `time|rounds_reps`), `benchmark_id` (FK a
  `wods.benchmarks`, NULL: `is_benchmark` se deriva) y `description` (0 a 2.000);
- CHECK `ck_wods_score_type`, `_title_length`, `_description_length` y `_time_cap` (rango y tipo
  de marca en una sola regla);
- índice `ix_wods_benchmark_id` (el conteo de WODs por benchmark y el filtro de la lista);
- triggers `wods_forbid_delete` y `wods_forbid_truncate` (`ENABLE ALWAYS`, `tgenabled = 'A'`) sobre
  `wods.forbid_mutation()` de `0032`: los WODs no se borran (RN-14).
`downgrade`: triggers, índices y tabla; los WODs guardados SE PIERDEN al bajar.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_wods_wods"
down_revision: str | None = "0033_wods_benchmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "wods"
TABLE: Final = "wods"
UQ_DATE: Final = "uq_wods_date"
IX_BENCHMARK: Final = "ix_wods_benchmark_id"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("score_type", "score_type IN ('time', 'rounds_reps', 'reps', 'load', 'none')"),
    ("title_length", "char_length(title) BETWEEN 1 AND 80"),
    ("description_length", "char_length(description) <= 2000"),
    (
        "time_cap",
        "time_cap_s IS NULL OR "
        "(time_cap_s BETWEEN 1 AND 14400 AND score_type IN ('time', 'rounds_reps'))",
    ),
)

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER wods_forbid_delete BEFORE DELETE ON wods.wods "
    "FOR EACH ROW EXECUTE FUNCTION wods.forbid_mutation()",
    "CREATE TRIGGER wods_forbid_truncate BEFORE TRUNCATE ON wods.wods "
    "FOR EACH STATEMENT EXECUTE FUNCTION wods.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE wods.wods ENABLE ALWAYS TRIGGER wods_forbid_delete",
    "ALTER TABLE wods.wods ENABLE ALWAYS TRIGGER wods_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS wods_forbid_truncate ON wods.wods",
    "DROP TRIGGER IF EXISTS wods_forbid_delete ON wods.wods",
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
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("score_type", sa.Text(), nullable=False),
        sa.Column("time_cap_s", sa.Integer(), nullable=True),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.ForeignKeyConstraint(
            ["benchmark_id"], ["wods.benchmarks.id"], name="fk_wods_benchmark_id"
        ),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(UQ_DATE, TABLE, ["date"], unique=True, schema=SCHEMA)
    op.create_index(IX_BENCHMARK, TABLE, ["benchmark_id"], schema=SCHEMA)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.drop_index(IX_BENCHMARK, table_name=TABLE, schema=SCHEMA)
    op.drop_index(UQ_DATE, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
