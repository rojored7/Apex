"""`athletes.personal_records` (S9-B1, US-180; S9-D8, S9-D18, S9-D31).

Revision ID: 0043_athletes_personal_records
Revises: 0042_athletes_body_metrics
Create Date: 2026-11-16

Tabla `athletes.personal_records` (tabla nueva sin datos; la invalidación va fundida aquí):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `member_id`; `kind` (`rm|benchmark`); `movement_id`, `benchmark_id` y `wod_id` sin FK entre
  esquemas; `value_g` (RM en gramos, 1 a 1.000.000); la marca de benchmark `level`, `seconds`,
  `rounds`, `reps`, `load_g` (mismos rangos que `results.wod_results`) y `capped`;
  `achieved_on` (fecha civil); `source` (`manual|derived`); `result_id`;
  `invalidated_at`, `invalidated_reason` (`superseded|voided|manual_error`), `invalidated_by` e
  `invalidated_by_result_id` (todas NULL al nacer). Ninguna columna cifrada.
- CHECK de forma (S9-D8): `rm` exige movimiento y valor y prohíbe benchmark y marca; `benchmark`
  exige benchmark y nivel y prohíbe movimiento y valor; `derived` exige `result_id` y `wod_id`,
  `manual` los prohíbe; `(invalidated_at IS NULL) = (invalidated_reason IS NULL)`;
  `manual_error` solo con `manual`, `superseded` y `voided` solo con `derived`; `capped` solo con
  `seconds` y `reps` y solo en un derivado; un benchmark lleva al menos una marca;
  `invalidated_by` va con `invalidated_at`; `invalidated_by_result_id` solo con `superseded`;
  `invalidated_at >= created_at` y `updated_at >= created_at`.
- Seis índices; los dos de vigentes llevan la columna desnuda `invalidated_at IS NULL` (S8-D50).

Guardas (`SECURITY INVOKER`, `search_path = pg_catalog`, `ENABLE ALWAYS`, S9-D31):
- `personal_records_guard_insert`: nace con las cuatro `invalidated_*` en NULL;
- `personal_records_guard_update`: nada cambia salvo las cuatro columnas de invalidación pasando
  (a la vez) de NULL a valor UNA sola vez y `updated_at` sin retroceder; una fila ya invalidada
  es terminal: ningún UPDATE posterior pasa, ni uno que no cambie nada; invalidar y cambiar otra
  columna en el mismo UPDATE falla;
- `personal_records_forbid_delete` y `personal_records_forbid_truncate`: nunca se borra
  (`athletes.forbid_mutation()` es de `0042`).
La auditoría la hace el hook del ORM (`__audited__`), no un trigger por tabla.

`downgrade`: triggers, funciones propias, índices y tabla; los récords guardados SE PIERDEN
(volcado previo `sprint-09-antes-0043.dump`, P-MIG 1). NO borra `athletes.forbid_mutation()` ni el
esquema: son de `0042`. SQL literal, sin interpolación de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043_athletes_personal_records"
down_revision: str | None = "0042_athletes_body_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "athletes"
TABLE: Final = "personal_records"
UQ_RESULT_KIND: Final = "uq_personal_records_result_kind"
IX_RM: Final = "ix_personal_records_rm"
IX_BENCH: Final = "ix_personal_records_bench"
IX_MEMBER_DATE: Final = "ix_personal_records_member_date"
IX_MOVEMENT: Final = "ix_personal_records_movement"
IX_BENCHMARK: Final = "ix_personal_records_benchmark"
TRIGGERS: Final[tuple[str, ...]] = (
    "personal_records_guard_insert",
    "personal_records_guard_update",
    "personal_records_forbid_delete",
    "personal_records_forbid_truncate",
)
FN_HEAD: Final = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$ "

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("kind", "kind IN ('rm', 'benchmark')"),
    ("source", "source IN ('manual', 'derived')"),
    ("level", "level IS NULL OR level IN ('rx', 'rx_plus', 'scaled')"),
    ("value_g", "value_g IS NULL OR value_g BETWEEN 1 AND 1000000"),
    ("seconds", "seconds IS NULL OR seconds BETWEEN 1 AND 86400"),
    ("rounds", "rounds IS NULL OR rounds BETWEEN 0 AND 1000"),
    ("reps", "reps IS NULL OR reps BETWEEN 0 AND 100000"),
    ("load_g", "load_g IS NULL OR load_g BETWEEN 0 AND 1000000"),
    ("capped_shape", "NOT capped OR (seconds IS NOT NULL AND reps IS NOT NULL)"),
    (
        "rm_shape",
        "kind <> 'rm' OR (movement_id IS NOT NULL AND value_g IS NOT NULL "
        "AND benchmark_id IS NULL AND level IS NULL AND seconds IS NULL AND rounds IS NULL "
        "AND reps IS NULL AND load_g IS NULL)",
    ),
    (
        "benchmark_shape",
        "kind <> 'benchmark' OR (benchmark_id IS NOT NULL AND level IS NOT NULL "
        "AND movement_id IS NULL AND value_g IS NULL "
        "AND num_nonnulls(seconds, rounds, reps, load_g) >= 1)",
    ),
    ("derived_shape", "source <> 'derived' OR (result_id IS NOT NULL AND wod_id IS NOT NULL)"),
    ("manual_shape", "source <> 'manual' OR (result_id IS NULL AND wod_id IS NULL)"),
    ("capped_manual", "source <> 'manual' OR NOT capped"),
    ("invalidated_pair", "(invalidated_at IS NULL) = (invalidated_reason IS NULL)"),
    ("invalidated_by_pair", "(invalidated_at IS NULL) = (invalidated_by IS NULL)"),
    (
        "invalidated_result_superseded",
        "invalidated_by_result_id IS NULL OR invalidated_reason = 'superseded'",
    ),
    ("invalidated_after_created", "invalidated_at IS NULL OR invalidated_at >= created_at"),
    ("updated_after_created", "updated_at >= created_at"),
    (
        "invalidated_reason_source",
        "invalidated_reason IS NULL "
        "OR (invalidated_reason = 'manual_error' AND source = 'manual') "
        "OR (invalidated_reason IN ('superseded', 'voided') AND source = 'derived')",
    ),
)

CREATE_FUNCTIONS: Final[tuple[str, ...]] = (
    "CREATE FUNCTION athletes.guard_personal_records_insert() RETURNS trigger " + FN_HEAD + "BEGIN "
    "IF NEW.invalidated_at IS NOT NULL OR NEW.invalidated_reason IS NOT NULL "
    "OR NEW.invalidated_by IS NOT NULL OR NEW.invalidated_by_result_id IS NOT NULL THEN "
    "RAISE EXCEPTION 'athletes.personal_records: un record nunca nace invalidado' "
    "USING ERRCODE = 'P0001'; END IF; "
    "RETURN NEW; END; $$",
    "CREATE FUNCTION athletes.guard_personal_records_update() RETURNS trigger " + FN_HEAD + "BEGIN "
    "IF OLD.invalidated_at IS NOT NULL THEN "
    "RAISE EXCEPTION 'athletes.personal_records: un record invalidado es terminal' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.id IS DISTINCT FROM OLD.id "
    "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
    "OR NEW.created_by IS DISTINCT FROM OLD.created_by "
    "OR NEW.member_id IS DISTINCT FROM OLD.member_id "
    "OR NEW.kind IS DISTINCT FROM OLD.kind "
    "OR NEW.movement_id IS DISTINCT FROM OLD.movement_id "
    "OR NEW.benchmark_id IS DISTINCT FROM OLD.benchmark_id "
    "OR NEW.wod_id IS DISTINCT FROM OLD.wod_id "
    "OR NEW.value_g IS DISTINCT FROM OLD.value_g "
    "OR NEW.level IS DISTINCT FROM OLD.level "
    "OR NEW.seconds IS DISTINCT FROM OLD.seconds "
    "OR NEW.rounds IS DISTINCT FROM OLD.rounds "
    "OR NEW.reps IS DISTINCT FROM OLD.reps "
    "OR NEW.load_g IS DISTINCT FROM OLD.load_g "
    "OR NEW.capped IS DISTINCT FROM OLD.capped "
    "OR NEW.achieved_on IS DISTINCT FROM OLD.achieved_on "
    "OR NEW.source IS DISTINCT FROM OLD.source "
    "OR NEW.result_id IS DISTINCT FROM OLD.result_id THEN "
    "RAISE EXCEPTION 'athletes.personal_records: el record registrado no cambia' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.updated_at < OLD.updated_at THEN "
    "RAISE EXCEPTION 'athletes.personal_records: updated_at no retrocede' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.updated_at IS DISTINCT FROM OLD.updated_at "
    "AND NEW.invalidated_at IS NOT DISTINCT FROM OLD.invalidated_at THEN "
    "RAISE EXCEPTION 'athletes.personal_records: updated_at solo cambia al invalidar' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.invalidated_at IS DISTINCT FROM OLD.invalidated_at "
    "OR NEW.invalidated_reason IS DISTINCT FROM OLD.invalidated_reason "
    "OR NEW.invalidated_by IS DISTINCT FROM OLD.invalidated_by "
    "OR NEW.invalidated_by_result_id IS DISTINCT FROM OLD.invalidated_by_result_id THEN "
    "IF NOT (OLD.invalidated_at IS NULL AND OLD.invalidated_reason IS NULL "
    "AND OLD.invalidated_by IS NULL AND OLD.invalidated_by_result_id IS NULL "
    "AND NEW.invalidated_at IS NOT NULL AND NEW.invalidated_reason IS NOT NULL "
    "AND NEW.invalidated_by IS NOT NULL) THEN "
    "RAISE EXCEPTION 'athletes.personal_records: la invalidacion es terminal' "
    "USING ERRCODE = 'P0001'; END IF; END IF; "
    "RETURN NEW; END; $$",
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER personal_records_guard_insert BEFORE INSERT ON athletes.personal_records "
    "FOR EACH ROW EXECUTE FUNCTION athletes.guard_personal_records_insert()",
    "CREATE TRIGGER personal_records_guard_update BEFORE UPDATE ON athletes.personal_records "
    "FOR EACH ROW EXECUTE FUNCTION athletes.guard_personal_records_update()",
    "CREATE TRIGGER personal_records_forbid_delete BEFORE DELETE ON athletes.personal_records "
    "FOR EACH ROW EXECUTE FUNCTION athletes.forbid_mutation()",
    "CREATE TRIGGER personal_records_forbid_truncate BEFORE TRUNCATE ON athletes.personal_records "
    "FOR EACH STATEMENT EXECUTE FUNCTION athletes.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = tuple(
    f"ALTER TABLE athletes.personal_records ENABLE ALWAYS TRIGGER {nombre}" for nombre in TRIGGERS
)
DROP_FUNCTIONS: Final[tuple[str, ...]] = (
    "DROP FUNCTION IF EXISTS athletes.guard_personal_records_update()",
    "DROP FUNCTION IF EXISTS athletes.guard_personal_records_insert()",
)


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # `clock_timestamp()` y no `now()` (S9-D52): `now()` es el inicio de la transacción; el
        # desempate N-45 («gana el más antiguo») y `updated_at >= created_at` necesitan el instante
        # real del INSERT, también para los récords derivados (B3).
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("movement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wod_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("value_g", sa.Integer(), nullable=True),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("seconds", sa.Integer(), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("load_g", sa.Integer(), nullable=True),
        sa.Column("capped", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("achieved_on", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invalidated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.Text(), nullable=True),
        sa.Column("invalidated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invalidated_by_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(
        UQ_RESULT_KIND,
        TABLE,
        ["result_id", "kind"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("result_id IS NOT NULL"),
    )
    op.create_index(
        IX_RM,
        TABLE,
        ["member_id", "movement_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("kind = 'rm' AND invalidated_at IS NULL"),
    )
    op.create_index(
        IX_BENCH,
        TABLE,
        ["member_id", "benchmark_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("kind = 'benchmark' AND invalidated_at IS NULL"),
    )
    op.create_index(
        IX_MEMBER_DATE,
        TABLE,
        ["member_id", sa.text("achieved_on DESC"), sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        IX_MOVEMENT,
        TABLE,
        ["movement_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("movement_id IS NOT NULL"),
    )
    op.create_index(
        IX_BENCHMARK,
        TABLE,
        ["benchmark_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("benchmark_id IS NOT NULL"),
    )
    for sentencia in (*CREATE_FUNCTIONS, *CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for nombre in reversed(TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {nombre} ON athletes.personal_records")
    for sentencia in DROP_FUNCTIONS:
        op.execute(sentencia)
    for indice in (IX_BENCHMARK, IX_MOVEMENT, IX_MEMBER_DATE, IX_BENCH, IX_RM, UQ_RESULT_KIND):
        op.drop_index(indice, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
