"""Firmas en la verificación de la cadena y validación del CHECK de la clave pública (S6-A3).

Revision ID: 0022_verify_signatures
Revises: 0021_audit_signatures
Create Date: 2026-11-11

`audit.verifications` gana seis columnas NULAS (S6-D10; US-142), sin valor por omisión: las
verificaciones anteriores a la migración conservan las seis en NULL y la pantalla las muestra como
«sin dato de firmas»:
- `signatures_checked` (`integer`) y `signatures_valid` (`integer`): firmas recorridas y válidas;
- `first_invalid_signature_seq` (`bigint`): `through_seq` de la primera firma inválida (o la que
  faltaba, regla anti-retroceso);
- `last_valid_signature_seq` (`bigint`), `last_valid_signature_at` (`timestamptz`) y
  `last_valid_signature_algorithm` (`text`): la última firma válida.
`ADD COLUMN` nula no reescribe la tabla ni toca los triggers `verifications_forbid_*` (`0013`,
`ENABLE ALWAYS` de `0014`) ni `signatures_forbid_*` (`0021`): siguen en `tgenabled = 'A'`.

S6-D99: `ALTER TABLE crypto.crypto_keys VALIDATE CONSTRAINT ck_crypto_keys_sign_public_key` (nació
`NOT VALID` en `0021`). Falla cerrado, y Alembic deja la base en `0021` (DDL transaccional), si
queda una fila `sign` sin clave pública: antes de subir se corre
`init-keys --data-class audit.signature` (RUNBOOK §14). La validación toma
`SHARE UPDATE EXCLUSIVE` sobre una tabla de unas pocas filas.

`downgrade` quita las seis columnas y nada más. [DECISIÓN DE DISEÑO] El CHECK se deja VALIDADO al
bajar: volver a `NOT VALID` no aporta (la tabla ya cumple la regla y `0021` lo recrea igual al
rehacer el ciclo) y evitaría detectar filas `sign` sin pública creadas después.
Todo el SQL es literal.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

revision: str = "0022_verify_signatures"
down_revision: str | None = "0021_audit_signatures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "audit"
TABLE: Final = "verifications"
VALIDATE_CHECK: Final = (
    "ALTER TABLE crypto.crypto_keys VALIDATE CONSTRAINT ck_crypto_keys_sign_public_key"
)


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("signatures_checked", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("signatures_valid", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE,
        sa.Column("first_invalid_signature_seq", sa.BigInteger(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE, sa.Column("last_valid_signature_seq", sa.BigInteger(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        TABLE,
        sa.Column("last_valid_signature_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE, sa.Column("last_valid_signature_algorithm", sa.Text(), nullable=True), schema=SCHEMA
    )
    op.execute(VALIDATE_CHECK)


def downgrade() -> None:
    for columna in (
        "last_valid_signature_algorithm",
        "last_valid_signature_at",
        "last_valid_signature_seq",
        "first_invalid_signature_seq",
        "signatures_valid",
        "signatures_checked",
    ):
        op.drop_column(TABLE, columna, schema=SCHEMA)
