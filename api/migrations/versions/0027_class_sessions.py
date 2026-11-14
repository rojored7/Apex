"""Sesiones de clase y su guarda (S7-B1, US-156; S7-D10, S7-D18, M-3).

Revision ID: 0027_class_sessions
Revises: 0026_class_slots
Create Date: 2026-11-14

Tabla `classes.class_sessions` (una clase concreta, generada desde una franja o extra):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `slot_id uuid` nulo (FK `RESTRICT` a `classes.class_slots`; nulo = sesión extra),
  `session_date date` (fecha civil de Bogotá), `starts_at timestamptz` (UTC), `duration_min`,
  `capacity`, `coach_id uuid` nulo (sin FK entre esquemas), `name text` nulo, `wod_id uuid` nulo
  (EP-22; sin FK), `status` (`scheduled` o `cancelled`; `done` se calcula al leer) y
  `cancel_reason`, `cancelled_by`, `cancelled_at` (los tres juntos con `cancelled`);
- CHECK `ck_class_sessions_status`, `_duration_min`, `_capacity`, `_name_length`,
  `_cancel_reason_length` y `_cancel_trio`;
- índices: único parcial `uq_class_sessions_slot_starts_at (slot_id, starts_at) WHERE slot_id IS
  NOT NULL` (US-156 CA2), `ix_class_sessions_starts_at` e `ix_class_sessions_session_date`;
- guarda `classes.guard_sessions_update()` (`BEFORE UPDATE`, `SECURITY INVOKER`, `search_path`
  `pg_catalog`): solo `scheduled -> cancelled`; una cancelada no cambia ni su estado ni
  `cancel_*`; `id`, `slot_id`, `session_date`, `starts_at`, `duration_min`, `capacity`, `coach_id`,
  `name`, `created_at` y `created_by` son inmutables (`wod_id` no: lo asigna EP-22);
- triggers `class_sessions_forbid_delete` y `_forbid_truncate` sobre `classes.forbid_mutation()` (de
  `0026`). Los tres `ENABLE ALWAYS` (`tgenabled = 'A'`). La auditoría la hace el hook del ORM.

`downgrade`: triggers, guarda y tabla. `classes.forbid_mutation()` y las franjas son de `0026`.
Las sesiones guardadas SE PIERDEN al bajar (el volcado previo de P-MIG las conserva).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_class_sessions"
down_revision: str | None = "0026_class_slots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "classes"
TABLE: Final = "class_sessions"
IX_UNIQUE: Final = "uq_class_sessions_slot_starts_at"
IX_STARTS: Final = "ix_class_sessions_starts_at"
IX_DATE: Final = "ix_class_sessions_session_date"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("status", "status IN ('scheduled', 'cancelled')"),
    ("duration_min", "duration_min BETWEEN 15 AND 240"),
    ("capacity", "capacity BETWEEN 1 AND 100"),
    ("name_length", "name IS NULL OR char_length(name) BETWEEN 1 AND 40"),
    (
        "cancel_reason_length",
        "cancel_reason IS NULL OR char_length(cancel_reason) BETWEEN 1 AND 200",
    ),
    (
        "cancel_trio",
        "(status = 'cancelled' AND cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL "
        "AND cancelled_at IS NOT NULL) OR (status = 'scheduled' AND cancel_reason IS NULL "
        "AND cancelled_by IS NULL AND cancelled_at IS NULL)",
    ),
)

CREATE_GUARD: Final = (
    "CREATE FUNCTION classes.guard_sessions_update() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN "
    "IF NEW.id IS DISTINCT FROM OLD.id OR NEW.slot_id IS DISTINCT FROM OLD.slot_id "
    "OR NEW.session_date IS DISTINCT FROM OLD.session_date "
    "OR NEW.starts_at IS DISTINCT FROM OLD.starts_at "
    "OR NEW.duration_min IS DISTINCT FROM OLD.duration_min "
    "OR NEW.capacity IS DISTINCT FROM OLD.capacity "
    "OR NEW.coach_id IS DISTINCT FROM OLD.coach_id "
    "OR NEW.name IS DISTINCT FROM OLD.name "
    "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
    "OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN "
    "RAISE EXCEPTION 'classes.class_sessions: la identidad de una sesion no cambia' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF OLD.status = 'cancelled' AND (NEW.status IS DISTINCT FROM OLD.status "
    "OR NEW.cancel_reason IS DISTINCT FROM OLD.cancel_reason "
    "OR NEW.cancelled_by IS DISTINCT FROM OLD.cancelled_by "
    "OR NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at) THEN "
    "RAISE EXCEPTION 'classes.class_sessions: una sesion cancelada no se modifica' "
    "USING ERRCODE = 'P0001'; END IF; "
    "RETURN NEW; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER class_sessions_guard_update BEFORE UPDATE ON classes.class_sessions "
    "FOR EACH ROW EXECUTE FUNCTION classes.guard_sessions_update()",
    "CREATE TRIGGER class_sessions_forbid_delete BEFORE DELETE ON classes.class_sessions "
    "FOR EACH ROW EXECUTE FUNCTION classes.forbid_mutation()",
    "CREATE TRIGGER class_sessions_forbid_truncate BEFORE TRUNCATE ON classes.class_sessions "
    "FOR EACH STATEMENT EXECUTE FUNCTION classes.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = tuple(
    f"ALTER TABLE classes.class_sessions ENABLE ALWAYS TRIGGER {nombre}"
    for nombre in (
        "class_sessions_guard_update",
        "class_sessions_forbid_delete",
        "class_sessions_forbid_truncate",
    )
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS class_sessions_forbid_truncate ON classes.class_sessions",
    "DROP TRIGGER IF EXISTS class_sessions_forbid_delete ON classes.class_sessions",
    "DROP TRIGGER IF EXISTS class_sessions_guard_update ON classes.class_sessions",
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
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classes.class_slots.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("coach_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("wod_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(
        IX_UNIQUE,
        TABLE,
        ["slot_id", "starts_at"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("slot_id IS NOT NULL"),
    )
    op.create_index(IX_STARTS, TABLE, ["starts_at"], schema=SCHEMA)
    op.create_index(IX_DATE, TABLE, ["session_date"], schema=SCHEMA)
    op.execute(CREATE_GUARD)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS classes.guard_sessions_update()")
    op.drop_index(IX_DATE, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_STARTS, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_UNIQUE, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
