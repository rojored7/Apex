"""Catálogo de movimientos y el esquema `wods` (S8-A1, US-165; S8-D5).

Revision ID: 0032_wods_movements
Revises: 0031_refresh_kiosk_path
Create Date: 2026-11-15

Esquema `wods` y tabla `wods.movements`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `name` (1 a 60), `name_norm` (1 a 60; NFKC, recorte, espacios colapsados y minúsculas, lo calcula
  `modules/wods/rules.py`), `category` (`weightlifting|gymnastics|monostructural|other`), `unit`
  (`kg|reps|m|cal|s`: qué se mide) e `is_active` (por defecto `true`);
- CHECK `ck_movements_category`, `_unit`, `_name_length` y `_name_norm_length`;
- índice único `uq_movements_name_norm (name_norm)`: la carrera de dos altas con el mismo nombre
  la decide la base;
- triggers `movements_forbid_delete` y `movements_forbid_truncate` (`ENABLE ALWAYS`,
  `tgenabled = 'A'`) sobre `wods.forbid_mutation()` (`SECURITY INVOKER`, `search_path`
  `pg_catalog`): los movimientos no se borran, se desactivan (RN-14). La auditoría de la tabla la
  hace el hook del ORM (`__audited__`), no un trigger.
Sin FK ni cruce con otros esquemas (N-37). `wods.forbid_mutation()` la reutilizan las migraciones
`0033` a `0035`: solo esta la crea y solo esta la borra.

`downgrade`: triggers, función, índice, tabla y esquema. Los movimientos guardados SE PIERDEN al
bajar; el volcado previo es `sprint-08-antes-0032.dump` (P-MIG, paso 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_wods_movements"
down_revision: str | None = "0031_refresh_kiosk_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "wods"
TABLE: Final = "movements"
UQ_NAME_NORM: Final = "uq_movements_name_norm"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("category", "category IN ('weightlifting', 'gymnastics', 'monostructural', 'other')"),
    ("unit", "unit IN ('kg', 'reps', 'm', 'cal', 's')"),
    ("name_length", "char_length(name) BETWEEN 1 AND 60"),
    ("name_norm_length", "char_length(name_norm) BETWEEN 1 AND 60"),
)

CREATE_FORBID: Final = (
    "CREATE FUNCTION wods.forbid_mutation() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'wods.% nunca se borran, se desactivan (% prohibido)', "
    "TG_TABLE_NAME, TG_OP USING ERRCODE = 'P0001'; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER movements_forbid_delete BEFORE DELETE ON wods.movements "
    "FOR EACH ROW EXECUTE FUNCTION wods.forbid_mutation()",
    "CREATE TRIGGER movements_forbid_truncate BEFORE TRUNCATE ON wods.movements "
    "FOR EACH STATEMENT EXECUTE FUNCTION wods.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE wods.movements ENABLE ALWAYS TRIGGER movements_forbid_delete",
    "ALTER TABLE wods.movements ENABLE ALWAYS TRIGGER movements_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS movements_forbid_truncate ON wods.movements",
    "DROP TRIGGER IF EXISTS movements_forbid_delete ON wods.movements",
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
    op.execute("CREATE SCHEMA IF NOT EXISTS wods")
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(UQ_NAME_NORM, TABLE, ["name_norm"], unique=True, schema=SCHEMA)
    op.execute(CREATE_FORBID)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS wods.forbid_mutation()")
    op.drop_index(UQ_NAME_NORM, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute("DROP SCHEMA IF EXISTS wods RESTRICT")
