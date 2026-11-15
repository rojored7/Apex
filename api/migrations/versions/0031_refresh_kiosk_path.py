"""`auth.refresh_tokens.kiosk_path`: la marca del modo quiosco en la sesión (S7-C4, S7-D41).

Revision ID: 0031_refresh_kiosk_path
Revises: 0030_memberships_end_guard
Create Date: 2026-11-14

Columna nula `kiosk_path text` con un CHECK de forma (`^/clases/<uuid>/checkin$`, UUID en
minúsculas): la ruta a la que queda confinada la sesión de la tablet. La marca se copia al
rotar el refresh y se borra con el logout. Sin DEFAULT ni relleno (filas viejas = sin marca).
`apex_api` ya tiene `SELECT, INSERT, UPDATE, DELETE` de tabla sobre `auth.refresh_tokens`
(P-ROL: sin cambio de grants). SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031_refresh_kiosk_path"
down_revision: str | None = "0030_memberships_end_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE auth.refresh_tokens ADD COLUMN kiosk_path text")
    op.execute(
        "ALTER TABLE auth.refresh_tokens ADD CONSTRAINT ck_refresh_tokens_kiosk_path_shape "
        "CHECK (kiosk_path IS NULL OR kiosk_path ~ "
        "'^/clases/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/checkin$')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE auth.refresh_tokens DROP CONSTRAINT ck_refresh_tokens_kiosk_path_shape")
    op.execute("ALTER TABLE auth.refresh_tokens DROP COLUMN kiosk_path")
