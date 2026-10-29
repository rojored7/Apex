"""Triggers inmutables en ALWAYS y mensaje de `audit.forbid_mutation()` por tabla (S4B-W0-2).

Revision ID: 0014_audit_log_triggers_always
Revises: 0013_audit_verifications
Create Date: 2026-10-29

- `CREATE OR REPLACE FUNCTION audit.forbid_mutation()`: el mensaje se construye con
  `TG_TABLE_SCHEMA`/`TG_TABLE_NAME` (S4B-D4, corregida por E5). La usan solo los cuatro triggers
  de `audit.audit_log` (0002) y `audit.verifications` (0013); `crypto.*` tiene funciones propias
  que no cambian. `SECURITY INVOKER` y `search_path = pg_catalog`; mismo ERRCODE `P0001`.
- `ENABLE ALWAYS TRIGGER` por nombre en los ocho triggers que estaban en `'O'`: los dos de
  `audit.audit_log` y los seis de `crypto.*` (S4B-D5). Con los dos de `verifications` (ya en
  `'A'` desde 0013) quedan diez: `session_replication_role = replica` ya no los salta.
- No crea tablas ni índices.

`downgrade`: los ocho vuelven a `'O'` (`ENABLE TRIGGER`), `verifications` sigue en `'A'` y la
función recupera el cuerpo literal de 0002.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_audit_log_triggers_always"
down_revision: str | None = "0013_audit_verifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Los ocho triggers que `0002` y `0003` crearon en modo `'O'`. SQL literal, sin f-strings.
ALWAYS_SQL: tuple[str, ...] = (
    "ALTER TABLE audit.audit_log ENABLE ALWAYS TRIGGER audit_log_forbid_mutation",
    "ALTER TABLE audit.audit_log ENABLE ALWAYS TRIGGER audit_log_forbid_truncate",
    "ALTER TABLE crypto.crypto_ops ENABLE ALWAYS TRIGGER crypto_ops_forbid_mutation",
    "ALTER TABLE crypto.crypto_ops ENABLE ALWAYS TRIGGER crypto_ops_forbid_truncate",
    "ALTER TABLE crypto.crypto_keys ENABLE ALWAYS TRIGGER crypto_keys_guard",
    "ALTER TABLE crypto.crypto_keys ENABLE ALWAYS TRIGGER crypto_keys_forbid_truncate",
    "ALTER TABLE crypto.crypto_jobs ENABLE ALWAYS TRIGGER crypto_jobs_guard",
    "ALTER TABLE crypto.crypto_jobs ENABLE ALWAYS TRIGGER crypto_jobs_forbid_truncate",
)
ORIGIN_SQL: tuple[str, ...] = (
    "ALTER TABLE audit.audit_log ENABLE TRIGGER audit_log_forbid_mutation",
    "ALTER TABLE audit.audit_log ENABLE TRIGGER audit_log_forbid_truncate",
    "ALTER TABLE crypto.crypto_ops ENABLE TRIGGER crypto_ops_forbid_mutation",
    "ALTER TABLE crypto.crypto_ops ENABLE TRIGGER crypto_ops_forbid_truncate",
    "ALTER TABLE crypto.crypto_keys ENABLE TRIGGER crypto_keys_guard",
    "ALTER TABLE crypto.crypto_keys ENABLE TRIGGER crypto_keys_forbid_truncate",
    "ALTER TABLE crypto.crypto_jobs ENABLE TRIGGER crypto_jobs_guard",
    "ALTER TABLE crypto.crypto_jobs ENABLE TRIGGER crypto_jobs_forbid_truncate",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION '%.% es append-only', TG_TABLE_SCHEMA, TG_TABLE_NAME
                USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    for sentencia in ALWAYS_SQL:
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in ORIGIN_SQL:
        op.execute(sentencia)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit.audit_log es append-only' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
