"""Cuentas de usuario, refresh tokens y tokens de un solo uso (US-041).

Revision ID: 0004_auth
Revises: 0003_crypto
Create Date: 2026-10-21

- `auth.users`: correo de login en claro (P5), `role` con CHECK, `member_id` obligatorio para
  `member` (S7), correo normalizado por CHECK y único entre no dados de baja.
- `auth.refresh_tokens`: `replaced_by_id` para detectar reuso (N-13).
- `auth.one_time_tokens`: activación y restablecimiento.
- INSERT del usuario técnico `system@apex.local` con UUID fijo (N-15): dato de referencia para
  llaves foráneas, única excepción a la regla de datos 8. No pasa por el hook de auditoría
  porque es la migración inicial; `is_active = false` y sin contraseña: nunca autentica.
El esquema `auth` lo crea 0001; aquí no se crea ni se borra.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_auth"
down_revision: str | None = "0003_crypto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


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
        "users",
        *common_columns(),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("locked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'coach', 'member')", name="role"),
        sa.CheckConstraint(
            "role <> 'member' OR member_id IS NOT NULL", name="member_id_for_member"
        ),
        sa.CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
        schema="auth",
    )
    op.create_index(
        "uq_users_email_alive",
        "users",
        ["email"],
        unique=True,
        schema="auth",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "refresh_tokens",
        *common_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", name="fk_refresh_tokens_user_id_users"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "replaced_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth.refresh_tokens.id", name="fk_refresh_tokens_replaced_by_id"),
            nullable=True,
        ),
        sa.Column("user_agent", sa.String(255), nullable=True),
        schema="auth",
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], schema="auth")

    op.create_table(
        "one_time_tokens",
        *common_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", name="fk_one_time_tokens_user_id_users"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('activate', 'reset')", name="purpose"),
        schema="auth",
    )
    op.create_index(
        "ix_ott_user_purpose_open",
        "one_time_tokens",
        ["user_id", "purpose"],
        schema="auth",
        postgresql_where=sa.text("used_at IS NULL"),
    )

    # N-15: usuario técnico. Dato de referencia (created_by, actor del worker y del CLI).
    op.execute(
        sa.text(
            "INSERT INTO auth.users "
            "(id, email, password_hash, role, member_id, is_active, created_by) "
            "VALUES (CAST(:id AS uuid), 'system@apex.local', NULL, 'admin', NULL, false, "
            "CAST(:id AS uuid))"
        ).bindparams(id=SYSTEM_USER_ID)
    )


def downgrade() -> None:
    op.drop_table("one_time_tokens", schema="auth")
    op.drop_table("refresh_tokens", schema="auth")
    op.drop_table("users", schema="auth")
