"""Membresías (S3-B1, US-083 y US-084; D8, D9, S3-D48, S3-D49, L-10).

Revision ID: 0008_memberships
Revises: 0007_plans
Create Date: 2026-10-25

Tabla `memberships.memberships`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`), `member_id` y `plan_id` (sin FK: otros
  esquemas, regla de módulos 2), `agreed_price_cop integer` (precio pactado, RN-04),
  `start_date` y `end_date` (`date`, fechas civiles de Bogotá con fin inclusivo, N-23),
  `classes_total` y `classes_remaining` (solo planes por clases, D15), `status` (seis valores),
  `cancel_reason`, `cancelled_by` y `cancelled_at` (solo en una `cancelled`);
- CHECKs nombrados (la convención les antepone `ck_memberships_`): precio > 0, fechas ordenadas,
  estados, clases > 0 y >= 0, el par de clases, restantes <= total, cancelada con motivo, quién y
  cuándo, motivo, quién y cuándo solo en una cancelada (revisión de seguridad de B1, L1) y motivo
  de 5 a 500 caracteres;
- `ex_memberships_member_dates` (D8): `EXCLUDE USING gist (member_id WITH =,
  daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')`; con `'[]'` dos
  membresías adyacentes (fin el 28, inicio el 29) no se solapan. `btree_gist` viene de `0001`;
- índices `ix_memberships_status_end_date`, `ix_memberships_member_status_start` e
  `ix_memberships_plan_id`.

Funciones (`plpgsql`, `SECURITY INVOKER`, `SET search_path = pg_catalog`, L-10), ambas con
`ERRCODE = integrity_constraint_violation` (23000) y `CONSTRAINT` con nombre, que asyncpg entrega en
`constraint_name` (`core.db.violated_constraint`):
- `memberships.guard_identity()` (`BEFORE UPDATE FOR EACH ROW`, D9 + S3-D48): no cambian `id`,
  `created_at`, `created_by` (revisión de seguridad de B1, L1), `member_id`, `plan_id`,
  `agreed_price_cop`, `start_date` ni `classes_total`; sobre una fila `cancelled` no cambian
  `status`, `cancel_reason`, `cancelled_by`, `cancelled_at`, `end_date` ni `classes_remaining`
  (una anulada es terminal). `CONSTRAINT = memberships_identity`;
- `memberships.forbid_delete()` (`BEFORE DELETE FOR EACH ROW` y `BEFORE TRUNCATE FOR EACH
  STATEMENT`): una membresía no se borra; se anula (B6). `CONSTRAINT = memberships_no_delete`.
Los tres triggers quedan en `ENABLE ALWAYS` (S3-D49, M-6): `session_replication_role = replica` no
los salta.

`downgrade` simétrico: tres triggers, dos funciones, índices y tabla (la `EXCLUDE` y los CHECKs caen
con la tabla). Nunca borra el esquema `memberships` (lo gestiona `0001`) ni `btree_gist`.
Todo el SQL es literal (sin interpolación). `common_columns()` se declara dentro del archivo porque
Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_memberships"
down_revision: str | None = "0007_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "memberships"
TABLE: Final = "memberships"
EXCLUDE_NAME: Final = "ex_memberships_member_dates"
INDEXES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("ix_memberships_status_end_date", ("status", "end_date")),
    ("ix_memberships_member_status_start", ("member_id", "status", "start_date")),
    ("ix_memberships_plan_id", ("plan_id",)),
)

CREATE_GUARD_IDENTITY: Final = """
CREATE FUNCTION memberships.guard_identity() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.created_by IS DISTINCT FROM OLD.created_by
        OR NEW.member_id IS DISTINCT FROM OLD.member_id
        OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.agreed_price_cop IS DISTINCT FROM OLD.agreed_price_cop
        OR NEW.start_date IS DISTINCT FROM OLD.start_date
        OR NEW.classes_total IS DISTINCT FROM OLD.classes_total
    THEN
        RAISE EXCEPTION 'memberships_identity: la identidad de la membresía no cambia'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'memberships_identity';
    END IF;
    IF OLD.status = 'cancelled' AND (
        NEW.status IS DISTINCT FROM OLD.status
        OR NEW.cancel_reason IS DISTINCT FROM OLD.cancel_reason
        OR NEW.cancelled_by IS DISTINCT FROM OLD.cancelled_by
        OR NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at
        OR NEW.end_date IS DISTINCT FROM OLD.end_date
        OR NEW.classes_remaining IS DISTINCT FROM OLD.classes_remaining
    ) THEN
        RAISE EXCEPTION 'memberships_identity: una membresía anulada no cambia'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'memberships_identity';
    END IF;
    RETURN NEW;
END;
$$
"""

CREATE_FORBID_DELETE: Final = """
CREATE FUNCTION memberships.forbid_delete() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'memberships_no_delete: una membresía no se borra; se anula'
        USING ERRCODE = 'integrity_constraint_violation',
              CONSTRAINT = 'memberships_no_delete';
END;
$$
"""

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER memberships_guard_identity BEFORE UPDATE ON memberships.memberships "
    "FOR EACH ROW EXECUTE FUNCTION memberships.guard_identity()",
    "CREATE TRIGGER memberships_forbid_delete BEFORE DELETE ON memberships.memberships "
    "FOR EACH ROW EXECUTE FUNCTION memberships.forbid_delete()",
    "CREATE TRIGGER memberships_forbid_truncate BEFORE TRUNCATE ON memberships.memberships "
    "FOR EACH STATEMENT EXECUTE FUNCTION memberships.forbid_delete()",
)

ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_guard_identity",
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_delete",
    "ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER memberships_forbid_truncate",
)

DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS memberships_forbid_truncate ON memberships.memberships",
    "DROP TRIGGER IF EXISTS memberships_forbid_delete ON memberships.memberships",
    "DROP TRIGGER IF EXISTS memberships_guard_identity ON memberships.memberships",
)

DROP_FUNCTIONS: Final[tuple[str, ...]] = (
    "DROP FUNCTION IF EXISTS memberships.forbid_delete()",
    "DROP FUNCTION IF EXISTS memberships.guard_identity()",
)


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


def _checks() -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint("agreed_price_cop > 0", name="agreed_price_positive"),
        sa.CheckConstraint("start_date <= end_date", name="dates_ordered"),
        sa.CheckConstraint(
            "status IN ('pending_payment', 'active', 'expiring', 'expired', 'frozen', 'cancelled')",
            name="status",
        ),
        sa.CheckConstraint("classes_total > 0", name="classes_total_positive"),
        sa.CheckConstraint("classes_remaining >= 0", name="classes_remaining_non_negative"),
        sa.CheckConstraint(
            "(classes_total IS NULL) = (classes_remaining IS NULL)", name="classes_pair"
        ),
        sa.CheckConstraint("classes_remaining <= classes_total", name="classes_remaining_le_total"),
        sa.CheckConstraint(
            "status <> 'cancelled' OR (cancel_reason IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancelled_at IS NOT NULL)",
            name="cancelled_has_reason",
        ),
        sa.CheckConstraint(
            "status = 'cancelled' OR (cancel_reason IS NULL AND cancelled_by IS NULL "
            "AND cancelled_at IS NULL)",
            name="cancel_fields_only_when_cancelled",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR char_length(cancel_reason) BETWEEN 5 AND 500",
            name="cancel_reason_length",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agreed_price_cop", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("classes_total", sa.Integer(), nullable=True),
        sa.Column("classes_remaining", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *_checks(),
        postgresql.ExcludeConstraint(
            ("member_id", "="),
            (sa.literal_column("daterange(start_date, end_date, '[]')"), "&&"),
            name=EXCLUDE_NAME,
            using="gist",
            where=sa.text("status <> 'cancelled'"),
        ),
        schema=SCHEMA,
    )
    for nombre, columnas in INDEXES:
        op.create_index(nombre, TABLE, list(columnas), schema=SCHEMA)
    op.execute(CREATE_GUARD_IDENTITY)
    op.execute(CREATE_FORBID_DELETE)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in (*DROP_TRIGGERS, *DROP_FUNCTIONS):
        op.execute(sentencia)
    for nombre, _columnas in reversed(INDEXES):
        op.drop_index(nombre, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
