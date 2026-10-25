"""Pagos (S3-B3, US-095; D17, D24, S3-D41, S3-D50).

Revision ID: 0010_payments
Revises: 0009_membership_freezes
Create Date: 2026-10-25

Tabla `payments.payments` (un pago por fila; inmutable por regla de datos 5):
- comunes (`id`, `created_at`, `updated_at`, `created_by`); `membership_id` y `member_id` (`uuid`,
  obligatorios, sin FK: la membresía vive en otro esquema, regla de módulos 2; `member_id` es la
  copia del socio que da el gate, D1); `amount_cop` (`bigint`), `method` (`text`), `reference`
  (`text`, nula), `paid_at` (`timestamptz`), `registered_by` (`uuid`); y las cuatro de anulación
  (`voided` `boolean` falso por defecto, `void_reason`, `voided_by`, `voided_at`, nulas);
- CHECKs nombrados (la convención les antepone `ck_payments_`): `amount_range` (1 a
  1.000.000.000, D17), `method` (los tres códigos de D24, en el mismo orden que
  `settings.schemas.PAYMENT_METHOD_CODES`; lo vigila `test_payment_method_codes`),
  `reference_length` (nula o de 1 a 64), `void_reason_length` (hasta 500) y `void_coherent` (las
  cuatro columnas de anulación juntas y el motivo visible; con `void_reason IS NOT NULL`
  explícito, porque `btrim(NULL) <> ''` es NULL y no haría falso el CHECK);
- índices `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id (membership_id)` e
  `ix_payments_member_paid (member_id, paid_at DESC)`.

Sin triggers: la inmutabilidad en la base llega con `0011_payments_immutability` (B4).
`downgrade` simétrico: índices y tabla. Nunca borra el esquema `payments` (lo gestiona `0001`).
Todo el SQL es literal (sin interpolación). `common_columns()` se declara dentro del archivo porque
Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_payments"
down_revision: str | None = "0009_membership_freezes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "payments"
TABLE: Final = "payments"
IX_PAID_AT: Final = "ix_payments_paid_at"
IX_MEMBERSHIP: Final = "ix_payments_membership_id"
IX_MEMBER_PAID: Final = "ix_payments_member_paid"

CHECK_AMOUNT_RANGE: Final = "amount_cop BETWEEN 1 AND 1000000000"
CHECK_METHOD: Final = "method IN ('cash', 'nequi', 'breb')"
CHECK_REFERENCE_LENGTH: Final = "reference IS NULL OR char_length(reference) BETWEEN 1 AND 64"
CHECK_VOID_REASON_LENGTH: Final = "void_reason IS NULL OR char_length(void_reason) <= 500"
CHECK_VOID_COHERENT: Final = (
    "(voided = false AND void_reason IS NULL AND voided_by IS NULL AND voided_at IS NULL) "
    "OR (voided = true AND void_reason IS NOT NULL AND btrim(void_reason) <> '' "
    "AND voided_by IS NOT NULL AND voided_at IS NOT NULL)"
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
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cop", sa.BigInteger(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("registered_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voided", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(CHECK_AMOUNT_RANGE, name="amount_range"),
        sa.CheckConstraint(CHECK_METHOD, name="method"),
        sa.CheckConstraint(CHECK_REFERENCE_LENGTH, name="reference_length"),
        sa.CheckConstraint(CHECK_VOID_REASON_LENGTH, name="void_reason_length"),
        sa.CheckConstraint(CHECK_VOID_COHERENT, name="void_coherent"),
        schema=SCHEMA,
    )
    op.create_index(IX_PAID_AT, TABLE, [sa.text("paid_at DESC")], schema=SCHEMA)
    op.create_index(IX_MEMBERSHIP, TABLE, ["membership_id"], schema=SCHEMA)
    op.create_index(IX_MEMBER_PAID, TABLE, ["member_id", sa.text("paid_at DESC")], schema=SCHEMA)


def downgrade() -> None:
    for indice in (IX_MEMBER_PAID, IX_MEMBERSHIP, IX_PAID_AT):
        op.drop_index(indice, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
