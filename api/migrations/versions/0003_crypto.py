"""Tablas del bus de criptografía: crypto_keys, crypto_ops y crypto_jobs (US-024).

Revision ID: 0003_crypto
Revises: 0002_audit_log
Create Date: 2026-10-21

- `crypto_keys`: material solo envuelto; una llave `active` por (purpose, data_class);
  `rotated_by` UUID (refinamiento de US-024); nunca se borra; solo cambian `state`,
  `rotated_at`, `rotated_by` y `updated_at`, con transiciones vigiladas por trigger.
- `crypto_ops`: append-only, con `count` (N-05), `purpose` (N-01) y `user_id NOT NULL`
  (N-15, sin FK a auth.users: 0004 corre después y core no depende de un módulo).
- `crypto_jobs`: un job en curso por clase (`coalesce(data_class, '*')`).
El esquema `crypto` lo crea 0001; aquí no se crea ni se borra.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_crypto"
down_revision: str | None = "0002_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERR = "USING ERRCODE = 'check_violation'"


def common_columns() -> list[sa.Column[object]]:
    """Igual que `migrations/helpers.py` (los archivos de versión no importan paquetes)."""
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


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "crypto_keys",
        *common_columns(),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("data_class", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("wrapped_material", sa.LargeBinary(), nullable=False),
        sa.Column("rotated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rotated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(f"purpose IN ({_in(('encrypt', 'index', 'sign'))})", name="purpose"),
        sa.CheckConstraint(r"data_class ~ '^[a-z_]+\.[a-z_]+$'", name="data_class"),
        sa.CheckConstraint(
            f"algorithm IN ({_in(('A256GCM', 'HMAC-SHA256', 'Ed25519', 'ML-DSA-65'))})",
            name="algorithm",
        ),
        sa.CheckConstraint(
            "(purpose = 'encrypt' AND algorithm = 'A256GCM') OR "
            "(purpose = 'index' AND algorithm = 'HMAC-SHA256') OR "
            "(purpose = 'sign' AND algorithm IN ('Ed25519', 'ML-DSA-65'))",
            name="purpose_algorithm",
        ),
        sa.CheckConstraint(f"provider IN ({_in(('local', 'openbao'))})", name="provider"),
        sa.CheckConstraint("version > 0", name="version"),
        sa.CheckConstraint(
            f"state IN ({_in(('active', 'decrypt_only', 'retired'))})", name="state"
        ),
        sa.UniqueConstraint("purpose", "data_class", "version", name="uq_crypto_keys_version"),
        schema="crypto",
    )
    op.create_index(
        "uq_crypto_keys_active",
        "crypto_keys",
        ["purpose", "data_class"],
        unique=True,
        schema="crypto",
        postgresql_where=sa.text("state = 'active'"),
    )

    op.create_table(
        "crypto_ops",
        *common_columns(),
        sa.Column("at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verb", sa.Text(), nullable=False),
        sa.Column("data_class", sa.Text(), nullable=True),
        sa.Column("key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key_version", sa.Integer(), nullable=True),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "verb IN ("
            + _in(
                (
                    "encrypt",
                    "decrypt",
                    "index",
                    "sign",
                    "verify",
                    "wrap",
                    "unwrap",
                    "rotate",
                    "export",
                )
            )
            + ")",
            name="verb",
        ),
        sa.CheckConstraint("result IN ('ok', 'error')", name="result"),
        sa.CheckConstraint("count >= 1", name="count"),
        schema="crypto",
    )
    op.create_index("ix_crypto_ops_at", "crypto_ops", [sa.text("at DESC")], schema="crypto")
    op.create_index(
        "ix_crypto_ops_data_class_at",
        "crypto_ops",
        ["data_class", sa.text("at DESC")],
        schema="crypto",
    )
    op.create_index("ix_crypto_ops_key_id", "crypto_ops", ["key_id"], schema="crypto")
    op.create_index(
        "ix_crypto_ops_batch_id",
        "crypto_ops",
        ["batch_id"],
        schema="crypto",
        postgresql_where=sa.text("batch_id IS NOT NULL"),
    )
    op.create_index(
        "ix_crypto_ops_record_id",
        "crypto_ops",
        ["record_id"],
        schema="crypto",
        postgresql_where=sa.text("record_id IS NOT NULL"),
    )

    op.create_table(
        "crypto_jobs",
        *common_columns(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("data_class", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"kind IN ({_in(('rotate', 'reencrypt', 'migrate_provider', 'rewrap'))})",
            name="kind",
        ),
        sa.CheckConstraint(
            f"status IN ({_in(('pending', 'running', 'done', 'failed'))})", name="status"
        ),
        sa.CheckConstraint("total >= 0", name="total"),
        sa.CheckConstraint("done >= 0 AND done <= total", name="done"),
        schema="crypto",
    )
    op.create_index(
        "uq_crypto_jobs_in_progress",
        "crypto_jobs",
        [sa.text("coalesce(data_class, '*')")],
        unique=True,
        schema="crypto",
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    op.execute(
        f"""
        CREATE FUNCTION crypto.forbid_ops_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'crypto.crypto_ops es append-only' {ERR};
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER crypto_ops_forbid_mutation BEFORE UPDATE OR DELETE ON crypto.crypto_ops "
        "FOR EACH ROW EXECUTE FUNCTION crypto.forbid_ops_mutation()"
    )
    op.execute(
        "CREATE TRIGGER crypto_ops_forbid_truncate BEFORE TRUNCATE ON crypto.crypto_ops "
        "FOR EACH STATEMENT EXECUTE FUNCTION crypto.forbid_ops_mutation()"
    )

    op.execute(
        f"""
        CREATE FUNCTION crypto.guard_keys_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                RAISE EXCEPTION 'crypto.crypto_keys: las llaves nunca se borran' {ERR};
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.purpose IS DISTINCT FROM OLD.purpose
               OR NEW.data_class IS DISTINCT FROM OLD.data_class
               OR NEW.algorithm IS DISTINCT FROM OLD.algorithm
               OR NEW.provider IS DISTINCT FROM OLD.provider
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.wrapped_material IS DISTINCT FROM OLD.wrapped_material
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
                RAISE EXCEPTION 'crypto.crypto_keys: solo cambia state y rotated_*' {ERR};
            END IF;
            IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
                (OLD.state = 'active' AND NEW.state IN ('decrypt_only', 'retired'))
                OR (OLD.state = 'decrypt_only' AND NEW.state = 'retired')
            ) THEN
                RAISE EXCEPTION 'crypto.crypto_keys: transición de estado no permitida (% -> %)',
                    OLD.state, NEW.state {ERR};
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER crypto_keys_guard BEFORE UPDATE OR DELETE ON crypto.crypto_keys "
        "FOR EACH ROW EXECUTE FUNCTION crypto.guard_keys_update()"
    )
    op.execute(
        "CREATE TRIGGER crypto_keys_forbid_truncate BEFORE TRUNCATE ON crypto.crypto_keys "
        "FOR EACH STATEMENT EXECUTE FUNCTION crypto.guard_keys_update()"
    )

    op.execute(
        f"""
        CREATE FUNCTION crypto.guard_jobs_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                RAISE EXCEPTION 'crypto.crypto_jobs: los jobs nunca se borran' {ERR};
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.kind IS DISTINCT FROM OLD.kind
               OR NEW.data_class IS DISTINCT FROM OLD.data_class
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
                RAISE EXCEPTION 'crypto.crypto_jobs: solo cambia el progreso' {ERR};
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER crypto_jobs_guard BEFORE UPDATE OR DELETE ON crypto.crypto_jobs "
        "FOR EACH ROW EXECUTE FUNCTION crypto.guard_jobs_mutation()"
    )
    op.execute(
        "CREATE TRIGGER crypto_jobs_forbid_truncate BEFORE TRUNCATE ON crypto.crypto_jobs "
        "FOR EACH STATEMENT EXECUTE FUNCTION crypto.guard_jobs_mutation()"
    )


def downgrade() -> None:
    for tabla, trigger in (
        ("crypto_jobs", "crypto_jobs_forbid_truncate"),
        ("crypto_jobs", "crypto_jobs_guard"),
        ("crypto_keys", "crypto_keys_forbid_truncate"),
        ("crypto_keys", "crypto_keys_guard"),
        ("crypto_ops", "crypto_ops_forbid_truncate"),
        ("crypto_ops", "crypto_ops_forbid_mutation"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON crypto.{tabla}")
    for funcion in ("guard_jobs_mutation", "guard_keys_update", "forbid_ops_mutation"):
        op.execute(f"DROP FUNCTION IF EXISTS crypto.{funcion}()")
    op.drop_table("crypto_jobs", schema="crypto")
    op.drop_table("crypto_ops", schema="crypto")
    op.drop_table("crypto_keys", schema="crypto")
