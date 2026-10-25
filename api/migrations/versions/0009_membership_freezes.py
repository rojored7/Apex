"""Congelaciones de membresías (S3-B2, US-089; D14, S3-D48, S3-D49, M-5, L-10).

Revision ID: 0009_membership_freezes
Revises: 0008_memberships
Create Date: 2026-10-25

Tabla `memberships.membership_freezes` (una fila por congelación; no hay columnas `frozen_*` en
`memberships`):
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `membership_id` con FK a
  `memberships.memberships(id)` (mismo esquema), `frozen_from` y `frozen_to` (`date`, ventana
  cerrada de Bogotá) y `days` (`integer`), todas obligatorias;
- CHECKs nombrados (la convención les antepone `ck_membership_freezes_`): `dates_ordered`
  (`frozen_from <= frozen_to`) y `days_match` (`days = (frozen_to - frozen_from) + 1`, RN-07);
- `ex_membership_freezes_dates`: `EXCLUDE USING gist (membership_id WITH =,
  daterange(frozen_from, frozen_to, '[]') WITH &&)`: dos ventanas de la misma membresía no se
  cruzan; adyacentes caben. `btree_gist` viene de `0001`;
- índice `ix_membership_freezes_membership (membership_id)`.

Solo se agregan filas (S3-D48, M-5): `memberships.forbid_freeze_mutation()` (`plpgsql`, `SECURITY
INVOKER`, `SET search_path = pg_catalog`, L-10) rechaza con `ERRCODE =
integrity_constraint_violation` (23000) y `CONSTRAINT = membership_freezes_append_only` todo
`UPDATE` (también uno sin cambios) y todo `DELETE` (trigger `membership_freezes_append_only`,
`BEFORE UPDATE OR DELETE FOR EACH ROW`) y el vaciado de la tabla (trigger
`membership_freezes_forbid_truncate`, `FOR EACH STATEMENT`). Los dos triggers quedan en `ENABLE
ALWAYS` (S3-D49): `session_replication_role = replica` no los salta.

`downgrade` simétrico: triggers, función, índice y tabla (la `EXCLUDE`, los CHECKs y la FK caen
con la tabla). Nunca borra el esquema `memberships` (lo gestiona `0001`), `btree_gist` ni las
funciones de `0008`. Todo el SQL es literal (sin interpolación). `common_columns()` se declara
dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_membership_freezes"
down_revision: str | None = "0008_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "memberships"
TABLE: Final = "membership_freezes"
EXCLUDE_NAME: Final = "ex_membership_freezes_dates"
INDEX_NAME: Final = "ix_membership_freezes_membership"

CREATE_FORBID_FREEZE_MUTATION: Final = """
CREATE FUNCTION memberships.forbid_freeze_mutation() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'membership_freezes_append_only: una congelación no cambia ni se borra'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'membership_freezes_append_only';
END;
$$
"""

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER membership_freezes_append_only BEFORE UPDATE OR DELETE "
    "ON memberships.membership_freezes "
    "FOR EACH ROW EXECUTE FUNCTION memberships.forbid_freeze_mutation()",
    "CREATE TRIGGER membership_freezes_forbid_truncate BEFORE TRUNCATE "
    "ON memberships.membership_freezes "
    "FOR EACH STATEMENT EXECUTE FUNCTION memberships.forbid_freeze_mutation()",
)

ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE memberships.membership_freezes "
    "ENABLE ALWAYS TRIGGER membership_freezes_append_only",
    "ALTER TABLE memberships.membership_freezes "
    "ENABLE ALWAYS TRIGGER membership_freezes_forbid_truncate",
)

DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS membership_freezes_forbid_truncate ON memberships.membership_freezes",
    "DROP TRIGGER IF EXISTS membership_freezes_append_only ON memberships.membership_freezes",
)

DROP_FUNCTION: Final = "DROP FUNCTION IF EXISTS memberships.forbid_freeze_mutation()"


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
        sa.Column(
            "membership_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memberships.memberships.id"),
            nullable=False,
        ),
        sa.Column("frozen_from", sa.Date(), nullable=False),
        sa.Column("frozen_to", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.CheckConstraint("frozen_from <= frozen_to", name="dates_ordered"),
        sa.CheckConstraint("days = (frozen_to - frozen_from) + 1", name="days_match"),
        postgresql.ExcludeConstraint(
            ("membership_id", "="),
            (sa.literal_column("daterange(frozen_from, frozen_to, '[]')"), "&&"),
            name=EXCLUDE_NAME,
            using="gist",
        ),
        schema=SCHEMA,
    )
    op.create_index(INDEX_NAME, TABLE, ["membership_id"], schema=SCHEMA)
    op.execute(CREATE_FORBID_FREEZE_MUTATION)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in (*DROP_TRIGGERS, DROP_FUNCTION):
        op.execute(sentencia)
    op.drop_index(INDEX_NAME, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
