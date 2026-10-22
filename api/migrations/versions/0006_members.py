"""Socios con cifrado en reposo e índices ciegos (S2-B7, US-069 y US-031; S2-D16, M-4, M-5).

Revision ID: 0006_members
Revises: 0005b_auth_security
Create Date: 2026-10-22

Tabla `members.members`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`) y `deleted_at` (borrado lógico);
- en claro: `first_name`, `last_name` (van al leaderboard), `sex`, `status` (default
  `'active'`), `document_type` (default `'CC'`, S2-D16), `data_consent_at` (lo fija el reloj
  del servidor, M-4) y `data_consent_version` (nula en v0.1);
- cifradas por el bus (`text`, blob `apx1.`): `document` (no nula), `phone`, `email`,
  `birth_date`, `emergency_contact`; índices ciegos `document_idx` (no nulo), `phone_idx`,
  `email_idx`;
- sin `notes` (M-5) y sin columnas `*_hint` (N-02);
- CHECKs nombrados: sexo, estado, tipo de documento, nombres no vacíos, cada blob `apx1.%` (un
  texto en claro se rechaza también por SQL crudo) y los pares valor/índice de teléfono y correo;
- único parcial `uq_members_document_idx_alive` (un dado de baja libera el documento) e índices
  `ix_members_phone_idx`, `ix_members_email_idx` y `ix_members_alive_last_name`.
El esquema `members` lo crea 0001; aquí no se crea ni se borra. `downgrade` borra la tabla.
`common_columns()` se declara dentro del archivo porque Alembic carga cada revisión por ruta.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_members"
down_revision: str | None = "0005b_auth_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "members"
TABLE = "members"
ENCRYPTED = ("document", "phone", "email", "birth_date", "emergency_contact")


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


def _blob_checks() -> list[sa.CheckConstraint]:
    # Nombres fijos de columna (constantes del archivo), no entrada externa.
    return [
        sa.CheckConstraint(f"{c} IS NULL OR {c} LIKE 'apx1.%'", name=f"{c}_blob") for c in ENCRYPTED
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("sex", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("document_type", sa.Text(), nullable=False, server_default=sa.text("'CC'")),
        sa.Column("data_consent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("data_consent_version", sa.Text(), nullable=True),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Text(), nullable=True),
        sa.Column("emergency_contact", sa.Text(), nullable=True),
        sa.Column("document_idx", sa.Text(), nullable=False),
        sa.Column("phone_idx", sa.Text(), nullable=True),
        sa.Column("email_idx", sa.Text(), nullable=True),
        sa.CheckConstraint("sex IN ('f', 'm', 'x')", name="sex"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="status"),
        sa.CheckConstraint("document_type IN ('CC', 'CE', 'TI', 'PA')", name="document_type"),
        sa.CheckConstraint("btrim(first_name) <> ''", name="first_name_not_blank"),
        sa.CheckConstraint("btrim(last_name) <> ''", name="last_name_not_blank"),
        *_blob_checks(),
        sa.CheckConstraint("(phone IS NULL) = (phone_idx IS NULL)", name="phone_idx_pair"),
        sa.CheckConstraint("(email IS NULL) = (email_idx IS NULL)", name="email_idx_pair"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_members_document_idx_alive",
        TABLE,
        ["document_idx"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_members_phone_idx", TABLE, ["phone_idx"], schema=SCHEMA)
    op.create_index("ix_members_email_idx", TABLE, ["email_idx"], schema=SCHEMA)
    op.create_index(
        "ix_members_alive_last_name",
        TABLE,
        ["last_name", "first_name"],
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
