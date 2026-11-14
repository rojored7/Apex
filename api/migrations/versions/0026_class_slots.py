"""Franjas del horario semanal y el esquema `classes` (S7-A2, US-155; S7-D9, S7-D18, M-3).

Revision ID: 0026_class_slots
Revises: 0025_s6_hardening
Create Date: 2026-11-14

Esquema `classes` y tabla `classes.class_slots` (una franja es UNA fila con varios días, como la
pantalla `Horario`):
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `weekdays smallint[]` (de 1 a 7 valores de 0 lunes a 6 domingo; el service los guarda sin repetir
  y ordenados), `start_time time` (hora local de Bogotá, N-40), `duration_min` (15 a 240),
  `capacity` (1 a 100), `default_coach_id uuid` nulo (sin FK entre esquemas; «Open box»),
  `name text` nulo (1 a 40), `valid_from date` e `is_active boolean` (por defecto `true`);
- CHECK `ck_class_slots_weekdays`, `_duration_min`, `_capacity` y `_name_length`;
- índice `ix_class_slots_is_active (is_active)`;
- triggers `class_slots_forbid_delete` y `class_slots_forbid_truncate` (`ENABLE ALWAYS`,
  `tgenabled = 'A'`) sobre `classes.forbid_mutation()` (`SECURITY INVOKER`, `search_path`
  `pg_catalog`): las franjas no se borran, se pausan (RN-14). La auditoría de la tabla la hace el
  hook del ORM (`__audited__`), no un trigger.
Sin FK ni cruce con otros esquemas (N-37). La unicidad «mismo día y hora entre activas» no cabe en
un índice sobre un arreglo: la comprueba el service bajo un candado asesor (S7-D9).

`downgrade`: triggers, función, tabla y esquema. Las franjas guardadas SE PIERDEN al bajar; la
tabla es nueva, así que el volcado previo es opcional (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_class_slots"
down_revision: str | None = "0025_s6_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "classes"
TABLE: Final = "class_slots"
IX_ACTIVE: Final = "ix_class_slots_is_active"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    (
        "weekdays",
        "cardinality(weekdays) BETWEEN 1 AND 7 "
        "AND weekdays <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]",
    ),
    ("duration_min", "duration_min BETWEEN 15 AND 240"),
    ("capacity", "capacity BETWEEN 1 AND 100"),
    ("name_length", "name IS NULL OR char_length(name) BETWEEN 1 AND 40"),
)

CREATE_FORBID: Final = (
    "CREATE FUNCTION classes.forbid_mutation() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'classes.% nunca se borran, se pausan (% prohibido)', "
    "TG_TABLE_NAME, TG_OP USING ERRCODE = 'P0001'; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER class_slots_forbid_delete BEFORE DELETE ON classes.class_slots "
    "FOR EACH ROW EXECUTE FUNCTION classes.forbid_mutation()",
    "CREATE TRIGGER class_slots_forbid_truncate BEFORE TRUNCATE ON classes.class_slots "
    "FOR EACH STATEMENT EXECUTE FUNCTION classes.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE classes.class_slots ENABLE ALWAYS TRIGGER class_slots_forbid_delete",
    "ALTER TABLE classes.class_slots ENABLE ALWAYS TRIGGER class_slots_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS class_slots_forbid_truncate ON classes.class_slots",
    "DROP TRIGGER IF EXISTS class_slots_forbid_delete ON classes.class_slots",
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
    op.execute("CREATE SCHEMA IF NOT EXISTS classes")
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("weekdays", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("default_coach_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(IX_ACTIVE, TABLE, ["is_active"], schema=SCHEMA)
    op.execute(CREATE_FORBID)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS classes.forbid_mutation()")
    op.drop_index(IX_ACTIVE, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute("DROP SCHEMA IF EXISTS classes RESTRICT")
