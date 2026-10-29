"""Bitácora de corridas del worker (S4A-B1, US-113; S4A-D3, S4A-D38, S4A-D55).

Revision ID: 0012_worker_job_runs
Revises: 0011_payments_immutability
Create Date: 2026-10-28

Tabla `worker.job_runs` (una fila por job y por día civil de Bogotá; el worker la reclama con
`INSERT ... ON CONFLICT (job_name, run_date) DO UPDATE` y la cierra al terminar cada intento):
- comunes (`id`, `created_at`, `updated_at`, `created_by`); `job_name` (`text`), `run_date`
  (`date`), `started_at` (`timestamptz`), `finished_at` (`timestamptz`, nula mientras corre),
  `result` (`text`), `error` (`text`, nula; solo el nombre del tipo de la excepción, S4A-D55) y
  `details` (`jsonb`, objeto vacío por defecto: conteos e intentos, nunca datos de personas);
- CHECKs nombrados (la convención les antepone `ck_job_runs_`): `job_name_shape` (minúscula
  inicial, minúsculas, dígitos y guion bajo, de 2 a 63 caracteres), `result` (`running`, `ok`,
  `error` y los cinco de backup de US-115, que llegan en v0.2: así no se edita una migración
  aplicada) y `finished_after_started`;
- índice único `uq_job_runs_name_date (job_name, run_date)` (el blanco del `ON CONFLICT`) e índice
  `ix_job_runs_name_started (job_name, started_at DESC)` (`last_run`, `--status`).
Sin triggers: el cierre del intento actualiza la fila. Sin `__audited__`: es bitácora operativa.

`downgrade` simétrico: los dos índices y la tabla. Nunca borra el esquema `worker` (lo gestiona
`0001`, cuyo `DROP SCHEMA ... RESTRICT` exige que quede vacío). Con el worker en marcha, pararlo
antes (`$DC stop worker`, RUNBOOK §6, enmienda E4). Todo el SQL es literal (sin interpolación).
`common_columns()` se declara dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_worker_job_runs"
down_revision: str | None = "0011_payments_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "worker"
TABLE: Final = "job_runs"
UQ_NAME_DATE: Final = "uq_job_runs_name_date"
IX_NAME_STARTED: Final = "ix_job_runs_name_started"

CHECK_JOB_NAME_SHAPE: Final = "job_name ~ '^[a-z][a-z0-9_]{1,62}$'"
CHECK_RESULT: Final = (
    "result IN ('running', 'ok', 'error', 'ok_unverified', 'stale', 'missing', 'corrupt', "
    "'undecryptable')"
)
CHECK_FINISHED_AFTER_STARTED: Final = "finished_at IS NULL OR finished_at >= started_at"


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
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(CHECK_JOB_NAME_SHAPE, name="job_name_shape"),
        sa.CheckConstraint(CHECK_RESULT, name="result"),
        sa.CheckConstraint(CHECK_FINISHED_AFTER_STARTED, name="finished_after_started"),
        schema=SCHEMA,
    )
    op.create_index(UQ_NAME_DATE, TABLE, ["job_name", "run_date"], unique=True, schema=SCHEMA)
    op.create_index(IX_NAME_STARTED, TABLE, ["job_name", sa.text("started_at DESC")], schema=SCHEMA)


def downgrade() -> None:
    for indice in (IX_NAME_STARTED, UQ_NAME_DATE):
        op.drop_index(indice, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
