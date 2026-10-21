"""Tabla de auditoría append-only con cadena de hashes (US-015).

Revision ID: 0002_audit_log
Revises: 0001_core_schemas
Create Date: 2026-10-21

- `audit.audit_log`: `seq` consecutivo sin DEFAULT (lo asigna `append_entry` bajo lock
  asesor; una secuencia dejaría huecos y N-30 los cuenta como ruptura), `prev_hash` y
  `hash` de 64 hex, `user_id` sin FK (auth.users llega en 0004), columnas espejo
  `created_at`/`updated_at`/`created_by` iguales a `at`/`user_id` por CHECK (regla de
  datos 3 sin dos verdades).
- `audit.forbid_mutation()`: rechaza UPDATE, DELETE y TRUNCATE (RN-14).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_audit_log"
down_revision: str | None = "0001_core_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("insert", "update", "delete", "reveal", "export", "download", "login", "verify")
HEX64 = "^[0-9a-f]{64}$"


def upgrade() -> None:
    acciones = ", ".join(f"'{a}'" for a in ACTIONS)
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("prev_hash", sa.CHAR(64), nullable=False),
        sa.Column("hash", sa.CHAR(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("seq >= 1", name="seq_positive"),
        sa.CheckConstraint(f"action IN ({acciones})", name="action"),
        sa.CheckConstraint(f"prev_hash ~ '{HEX64}'", name="prev_hash_hex"),
        sa.CheckConstraint(f"hash ~ '{HEX64}'", name="hash_hex"),
        sa.CheckConstraint(
            "created_at = at AND updated_at = at AND created_by = user_id", name="mirror"
        ),
        schema="audit",
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"], schema="audit")
    op.create_index(
        "ix_audit_log_table_record", "audit_log", ["table_name", "record_id"], schema="audit"
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"], schema="audit")
    op.create_index(
        "ix_audit_log_table_seq",
        "audit_log",
        ["table_name", sa.text("seq DESC")],
        schema="audit",
    )
    op.create_index(
        "ix_audit_log_subject_member_seq",
        "audit_log",
        ["subject_member_id", sa.text("seq DESC")],
        schema="audit",
    )
    op.execute(
        """
        CREATE FUNCTION audit.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit.audit_log es append-only' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_forbid_mutation BEFORE UPDATE OR DELETE ON audit.audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_forbid_truncate BEFORE TRUNCATE ON audit.audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_forbid_truncate ON audit.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_forbid_mutation ON audit.audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit.forbid_mutation()")
    op.drop_table("audit_log", schema="audit")
