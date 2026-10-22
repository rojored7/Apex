"""Seguridad de sesión en `auth` (S2-B2; S2-D9, H-3, L-4, M-8 y L-10).

Revision ID: 0005b_auth_security
Revises: 0005_settings
Create Date: 2026-10-22

Cuatro columnas nuevas y un CHECK, sin tocar `0004_auth`:
- `auth.users.must_change_password boolean NOT NULL DEFAULT false`: el admin sembrado y los
  enlaces entregados a mano obligan a cambiarla (M-8).
- `auth.users.failed_login_count integer NOT NULL DEFAULT 0` con
  `ck_users_failed_login_count_non_negative`: fallos consecutivos de login; se incrementa con
  `UPDATE ... RETURNING` (L-10) y decide el bloqueo persistente (S2-D10).
- `auth.users.tokens_valid_after timestamptz NULL`: corte de los access ya emitidos (H-3); lo
  fija `revoke_all` con el reloj de la app truncado a segundos.
- `auth.refresh_tokens.family_started_at timestamptz NOT NULL DEFAULT now()`: inicio de la
  familia de refresh para el tope absoluto de 30 días (L-4); el api lo escribe siempre con su
  reloj y la rotación lo hereda. El default solo llena las filas que ya existían.
`downgrade` quita el CHECK y las cuatro columnas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005b_auth_security"
down_revision: str | None = "0005_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_FALLOS = "ck_users_failed_login_count_non_negative"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="auth",
    )
    op.add_column(
        "users",
        sa.Column("tokens_valid_after", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="auth",
    )
    op.create_check_constraint(
        op.f(CHECK_FALLOS), "users", "failed_login_count >= 0", schema="auth"
    )
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "family_started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "family_started_at", schema="auth")
    op.drop_constraint(op.f(CHECK_FALLOS), "users", schema="auth", type_="check")
    op.drop_column("users", "tokens_valid_after", schema="auth")
    op.drop_column("users", "failed_login_count", schema="auth")
    op.drop_column("users", "must_change_password", schema="auth")
