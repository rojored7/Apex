"""Firmas de la cadena de auditoría y clave pública de las llaves de firma (S6-A1, US-140).

Revision ID: 0021_audit_signatures
Revises: 0020_notifications_indexes
Create Date: 2026-11-11

Tabla `audit.signatures` (S6-D7; append-only; una fila por firma de la cadena):
- comunes (`id`, `created_at`, `updated_at`, `created_by`); `through_seq` (`bigint`, único, la fila
  de la cadena que se firmó), `hash` (`char(64)`, el hash de esa fila), `signature` (`text`, el
  blob `apx1.<key_id>.<alg>.<sig>`), `key_id` (`uuid`, llave foránea `ON DELETE RESTRICT` a
  `crypto.crypto_keys(id)`: `verify` elige la clave pública por `key_id`, así que una firma no
  puede apuntar a una llave inexistente; sin índice propio), `algorithm`,
  `payload_version` (`smallint`, 1) y `signed_at`;
- CHECKs: `through_seq_positive`, `hash_shape` (64 hexadecimales en minúscula; `char(64)` rellena
  con espacios, que el patrón rechaza al compararse como `text`), `algorithm` (`Ed25519`,
  `ML-DSA-65`) y `payload_version_positive`;
- índices: único sobre `through_seq` y `ix_signatures_signed_at (signed_at DESC)`;
- función `audit.forbid_signature_mutation()` y triggers `signatures_forbid_mutation`
  (`BEFORE UPDATE OR DELETE`, por fila) y `signatures_forbid_truncate` (`BEFORE TRUNCATE`), con
  `ENABLE ALWAYS` como en `0014` (siguen disparando con `session_replication_role = replica`).
Sin `__audited__`: auditaría la auditoría; la firma deja su rastro en `crypto_ops(verb=sign)`.

`crypto.crypto_keys.public_key` (S6-D81): `text` nula (base64 de los 32 bytes de la clave pública
Ed25519) con CHECK `(purpose <> 'sign') OR (public_key IS NOT NULL)` creado `NOT VALID` (S6-D99):
rechaza toda fila nueva o actualizada sin clave pública pero tolera una fila `sign` anterior sin
ella; `init-keys --data-class audit.signature` (A2) la completa y la migración `0022` (A3) hace
`VALIDATE CONSTRAINT`. No reescribe filas.

`downgrade` simétrico: CHECK y columna, triggers, función y tabla. Todo el SQL es literal.
`common_columns()` se declara dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_audit_signatures"
down_revision: str | None = "0020_notifications_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "audit"
TABLE: Final = "signatures"
IX_THROUGH_SEQ: Final = "uq_signatures_through_seq"
IX_SIGNED_AT: Final = "ix_signatures_signed_at"
CK_SIGN_PUBLIC_KEY: Final = "ck_crypto_keys_sign_public_key"

CHECK_THROUGH_SEQ: Final = "through_seq > 0"
CHECK_HASH_SHAPE: Final = "hash::text ~ '^[0-9a-f]{64}$'"
CHECK_ALGORITHM: Final = "algorithm IN ('Ed25519', 'ML-DSA-65')"
CHECK_PAYLOAD_VERSION: Final = "payload_version >= 1"

CREATE_FUNCTION: Final = (
    "CREATE FUNCTION audit.forbid_signature_mutation() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'audit.signatures es append-only' USING ERRCODE = 'P0001'; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER signatures_forbid_mutation BEFORE UPDATE OR DELETE ON audit.signatures "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_signature_mutation()",
    "CREATE TRIGGER signatures_forbid_truncate BEFORE TRUNCATE ON audit.signatures "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_signature_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE audit.signatures ENABLE ALWAYS TRIGGER signatures_forbid_mutation",
    "ALTER TABLE audit.signatures ENABLE ALWAYS TRIGGER signatures_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS signatures_forbid_truncate ON audit.signatures",
    "DROP TRIGGER IF EXISTS signatures_forbid_mutation ON audit.signatures",
)
ADD_PUBLIC_KEY: Final = "ALTER TABLE crypto.crypto_keys ADD COLUMN public_key text"
ADD_CHECK: Final = (
    "ALTER TABLE crypto.crypto_keys ADD CONSTRAINT ck_crypto_keys_sign_public_key "
    "CHECK ((purpose <> 'sign') OR (public_key IS NOT NULL)) NOT VALID"
)
DROP_CHECK: Final = (
    "ALTER TABLE crypto.crypto_keys DROP CONSTRAINT IF EXISTS ck_crypto_keys_sign_public_key"
)
DROP_PUBLIC_KEY: Final = "ALTER TABLE crypto.crypto_keys DROP COLUMN IF EXISTS public_key"


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
        sa.Column("through_seq", sa.BigInteger(), nullable=False),
        sa.Column("hash", sa.CHAR(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column(
            "payload_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["key_id"],
            ["crypto.crypto_keys.id"],
            name="fk_signatures_key_id_crypto_keys",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(CHECK_THROUGH_SEQ, name="through_seq_positive"),
        sa.CheckConstraint(CHECK_HASH_SHAPE, name="hash_shape"),
        sa.CheckConstraint(CHECK_ALGORITHM, name="algorithm"),
        sa.CheckConstraint(CHECK_PAYLOAD_VERSION, name="payload_version_positive"),
        schema=SCHEMA,
    )
    op.create_index(IX_THROUGH_SEQ, TABLE, ["through_seq"], unique=True, schema=SCHEMA)
    # `signed_at DESC`: lo pide S6-D7 y A3 lo consume en `GET /audit/signatures/latest`.
    op.create_index(IX_SIGNED_AT, TABLE, [sa.text("signed_at DESC")], schema=SCHEMA)
    op.execute(CREATE_FUNCTION)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)
    op.execute(ADD_PUBLIC_KEY)
    op.execute(ADD_CHECK)


def downgrade() -> None:
    op.execute(DROP_CHECK)
    op.execute(DROP_PUBLIC_KEY)
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS audit.forbid_signature_mutation()")
    op.drop_index(IX_SIGNED_AT, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_THROUGH_SEQ, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
