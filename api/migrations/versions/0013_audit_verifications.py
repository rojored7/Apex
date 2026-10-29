"""Verificaciones de la cadena de auditoría (S4A-B3, US-104, US-105; S4A-D38, S4A-D43).

Revision ID: 0013_audit_verifications
Revises: 0012_worker_job_runs
Create Date: 2026-10-28

Tabla `audit.verifications` (una fila por verificación terminada, de la API o de la CLI; la
última `ok` es el ancla de la siguiente, H-1):
- comunes (`id`, `created_at`, `updated_at`, `created_by`); `started_at` y `finished_at`
  (`timestamptz`), `through_seq` (`bigint`, el `max(seq)` recorrido), `through_hash`
  (`char(64)`, el `hash` de la fila `through_seq` o `ZERO_HASH` con la cadena vacía),
  `rows_checked` (`bigint`), `ok` (`boolean`), `broken_at_seq` (`bigint`, nula si `ok`),
  `triggered_by` (`uuid`) y `source` (`text`);
- CHECKs nombrados (la convención les antepone `ck_verifications_`): `through_seq_non_negative`,
  `rows_checked_non_negative`, `source` (`api`, `cli`), `ok_matches_broken` (`ok` sin
  `broken_at_seq`, no `ok` con un `broken_at_seq` positivo), `finished_after_started` y
  `through_hash_shape` (64 hexadecimales en minúscula; `char(64)` rellena con espacios, que el
  patrón rechaza al compararse como `text`);
- índice `ix_verifications_finished_at (finished_at DESC)` (`last_verification` y el ancla);
- triggers `verifications_forbid_mutation` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) y
  `verifications_forbid_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`) sobre la función
  EXISTENTE `audit.forbid_mutation()` de `0002` (no se redefine), los dos con `ENABLE ALWAYS`
  (S3-D49): siguen disparando con `session_replication_role = replica`.
Sin `__audited__`: su resultado entra a la cadena como fila `verify` (N-30, S4A-D12).

`downgrade` simétrico: triggers, índice y tabla; nunca la función (la usa `audit.audit_log`). Las
filas `verify` de la cadena se quedan (la cadena es inmutable). No hace falta parar el worker
(no toca `worker`, enmienda E4). Todo el SQL es literal (sin interpolación). `common_columns()` se
declara dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_audit_verifications"
down_revision: str | None = "0012_worker_job_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "audit"
TABLE: Final = "verifications"
IX_FINISHED_AT: Final = "ix_verifications_finished_at"

CHECK_THROUGH_SEQ: Final = "through_seq >= 0"
CHECK_ROWS_CHECKED: Final = "rows_checked >= 0"
CHECK_SOURCE: Final = "source IN ('api', 'cli')"
CHECK_OK_MATCHES_BROKEN: Final = (
    "(ok AND broken_at_seq IS NULL) OR (NOT ok AND broken_at_seq IS NOT NULL AND broken_at_seq > 0)"
)
CHECK_FINISHED_AFTER_STARTED: Final = "started_at <= finished_at"
CHECK_THROUGH_HASH_SHAPE: Final = "through_hash::text ~ '^[0-9a-f]{64}$'"

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER verifications_forbid_mutation BEFORE UPDATE OR DELETE ON audit.verifications "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()",
    "CREATE TRIGGER verifications_forbid_truncate BEFORE TRUNCATE ON audit.verifications "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE audit.verifications ENABLE ALWAYS TRIGGER verifications_forbid_mutation",
    "ALTER TABLE audit.verifications ENABLE ALWAYS TRIGGER verifications_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS verifications_forbid_truncate ON audit.verifications",
    "DROP TRIGGER IF EXISTS verifications_forbid_mutation ON audit.verifications",
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


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("through_seq", sa.BigInteger(), nullable=False),
        sa.Column("through_hash", sa.CHAR(64), nullable=False),
        sa.Column("rows_checked", sa.BigInteger(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("broken_at_seq", sa.BigInteger(), nullable=True),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint(CHECK_THROUGH_SEQ, name="through_seq_non_negative"),
        sa.CheckConstraint(CHECK_ROWS_CHECKED, name="rows_checked_non_negative"),
        sa.CheckConstraint(CHECK_SOURCE, name="source"),
        sa.CheckConstraint(CHECK_OK_MATCHES_BROKEN, name="ok_matches_broken"),
        sa.CheckConstraint(CHECK_FINISHED_AFTER_STARTED, name="finished_after_started"),
        sa.CheckConstraint(CHECK_THROUGH_HASH_SHAPE, name="through_hash_shape"),
        schema=SCHEMA,
    )
    op.create_index(IX_FINISHED_AT, TABLE, [sa.text("finished_at DESC")], schema=SCHEMA)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.drop_index(IX_FINISHED_AT, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
