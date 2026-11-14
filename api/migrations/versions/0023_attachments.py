"""Esquema `attachments`, tabla `attachments.attachments` y su inmutabilidad (S6-C1, US-147).

Revision ID: 0023_attachments
Revises: 0022_verify_signatures
Create Date: 2026-11-12

Crea el esquema `attachments` y la tabla `attachments.attachments` (S6-D25): metadatos de cada
archivo subido; el contenido vive en el almacenamiento de objetos, nunca en la base. Sin llaves
foráneas hacia otros esquemas (`owner_id` es una referencia lógica; `key_id` la reforzó `0025`
con la FK `fk_attachments_key_id` hacia `crypto.crypto_keys`, S7-D3).
- `owner_table` solo `members` (v0.3); `kind` `photo|consent|other`; `filename_random` único de 32
  hexadecimales en minúscula (es la clave del objeto); `mime` de tres tipos; `size_bytes` entre 1
  y 5.242.880; `storage_provider` `local|s3`.
- `sensitive` es obligatorio con `kind = 'consent'` y `sensitive = (key_id IS NOT NULL)`: un archivo
  sensible siempre tiene llave y uno que no lo es nunca la tiene.
- Índice `(owner_table, owner_id, kind, created_at DESC)` para «la foto vigente» y las listas.

Inmutabilidad (tres triggers `ENABLE ALWAYS`, `tgenabled = 'A'`, que `session_replication_role =
replica` no apaga; funciones `SECURITY INVOKER` con `SET search_path = pg_catalog`, como A1):
- `attachments_guard_update`: un `UPDATE` solo puede cambiar `key_id` y `updated_at` (el recifrado);
- `attachments_forbid_delete` y `attachments_forbid_truncate`: la tabla es de solo inserción.
El `DROP TABLE` del `downgrade` no dispara el trigger de `DELETE`.

S6-D108: el índice `ix_crypto_ops_user_id_at` sobre `crypto.crypto_ops (user_id, at DESC)` acelera
el filtro por usuario de la bitácora de llaves (B2). S6-D112: el índice parcial
`ix_attachments_key_id (key_id) WHERE key_id IS NOT NULL` sirve `count_by_key`, `count_pending` y la
selección del lote de recifrado sin recorrer la tabla. Todo el SQL es literal.

`downgrade` quita triggers, funciones, índices, tabla y esquema. Los objetos del volumen `uploads`
quedan huérfanos y los detecta `attachments-check` (RUNBOOK §6).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_attachments"
down_revision: str | None = "0022_verify_signatures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "attachments"
TABLE: Final = "attachments"
IX_OWNER: Final = "ix_attachments_owner_kind_created"
IX_KEY: Final = "ix_attachments_key_id"  # parcial (S6-D112)
IX_OPS_USER: Final = "ix_crypto_ops_user_id_at"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("owner_table", "owner_table IN ('members')"),
    ("kind", "kind IN ('photo', 'consent', 'other')"),
    ("filename_random_shape", "filename_random ~ '^[0-9a-f]{32}$'"),
    ("mime", "mime IN ('image/jpeg', 'image/png', 'application/pdf')"),
    ("size_bytes", "size_bytes BETWEEN 1 AND 5242880"),
    ("storage_provider", "storage_provider IN ('local', 's3')"),
    ("consent_sensitive", "kind <> 'consent' OR sensitive"),
    ("sensitive_key", "sensitive = (key_id IS NOT NULL)"),
)

CREATE_GUARD: Final = (
    "CREATE FUNCTION attachments.guard_update() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'attachments.attachments solo admite cambiar key_id y updated_at' "
    "USING ERRCODE = 'P0001'; END; $$"
)
# `UPDATE OF <columnas>` dispara aunque el valor no cambie: tocar una columna inmutable es el error.
GUARDED_COLUMNS: Final = (
    "id, created_at, created_by, owner_table, owner_id, kind, filename_random, mime, "
    "size_bytes, sensitive, storage_provider, uploaded_by"
)
CREATE_FORBID: Final = (
    "CREATE FUNCTION attachments.forbid_mutation() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'attachments.attachments es append-only (solo inserción)' "
    "USING ERRCODE = 'P0001'; END; $$"
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    f"CREATE TRIGGER attachments_guard_update BEFORE UPDATE OF {GUARDED_COLUMNS} "
    "ON attachments.attachments "
    "FOR EACH ROW EXECUTE FUNCTION attachments.guard_update()",
    "CREATE TRIGGER attachments_forbid_delete BEFORE DELETE ON attachments.attachments "
    "FOR EACH ROW EXECUTE FUNCTION attachments.forbid_mutation()",
    "CREATE TRIGGER attachments_forbid_truncate BEFORE TRUNCATE ON attachments.attachments "
    "FOR EACH STATEMENT EXECUTE FUNCTION attachments.forbid_mutation()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE attachments.attachments ENABLE ALWAYS TRIGGER attachments_guard_update",
    "ALTER TABLE attachments.attachments ENABLE ALWAYS TRIGGER attachments_forbid_delete",
    "ALTER TABLE attachments.attachments ENABLE ALWAYS TRIGGER attachments_forbid_truncate",
)
DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS attachments_forbid_truncate ON attachments.attachments",
    "DROP TRIGGER IF EXISTS attachments_forbid_delete ON attachments.attachments",
    "DROP TRIGGER IF EXISTS attachments_guard_update ON attachments.attachments",
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
    op.execute("CREATE SCHEMA IF NOT EXISTS attachments")
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("owner_table", sa.Text(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename_random", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False),
        sa.Column("key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_provider", sa.Text(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(
        "uq_attachments_filename_random", TABLE, ["filename_random"], unique=True, schema=SCHEMA
    )
    op.create_index(
        IX_OWNER,
        TABLE,
        ["owner_table", "owner_id", "kind", sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        IX_KEY,
        TABLE,
        ["key_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("key_id IS NOT NULL"),
    )
    op.execute(CREATE_GUARD)
    op.execute(CREATE_FORBID)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)
    op.create_index(IX_OPS_USER, "crypto_ops", ["user_id", sa.text("at DESC")], schema="crypto")


def downgrade() -> None:
    op.drop_index(IX_OPS_USER, table_name="crypto_ops", schema="crypto")
    for sentencia in DROP_TRIGGERS:
        op.execute(sentencia)
    op.execute("DROP FUNCTION IF EXISTS attachments.guard_update()")
    op.execute("DROP FUNCTION IF EXISTS attachments.forbid_mutation()")
    op.drop_index(IX_KEY, table_name=TABLE, schema=SCHEMA)
    op.drop_index(IX_OWNER, table_name=TABLE, schema=SCHEMA)
    op.drop_index("uq_attachments_filename_random", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute("DROP SCHEMA IF EXISTS attachments")
