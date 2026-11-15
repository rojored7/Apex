"""`auth.refresh_tokens.kiosk_path` acepta la ruta de resultados (S8-B3, S8-D15, L-5).

Revision ID: 0038_kiosk_results_path
Revises: 0037_results_immutability
Create Date: 2026-11-15

Reemplaza el CHECK `ck_refresh_tokens_kiosk_path_shape` de `0031` CONSERVANDO su nombre (lo fijan
`test_0031`) por `^/clases/<uuid>/(checkin|resultados)$`, UUID en minúsculas. Es más amplio: ninguna
fila existente lo viola. El `downgrade` reescribe `.../resultados` a `.../checkin` (la misma clase)
antes de restaurar el CHECK de `0031`, para que no falle con filas nuevas (L-5). Sin cambio de
grants. SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038_kiosk_results_path"
down_revision: str | None = "0037_results_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE auth.refresh_tokens DROP CONSTRAINT ck_refresh_tokens_kiosk_path_shape")
    op.execute(
        "ALTER TABLE auth.refresh_tokens ADD CONSTRAINT ck_refresh_tokens_kiosk_path_shape "
        "CHECK (kiosk_path IS NULL OR kiosk_path ~ "
        "'^/clases/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
        "(checkin|resultados)$')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE auth.refresh_tokens DROP CONSTRAINT ck_refresh_tokens_kiosk_path_shape")
    op.execute(
        "UPDATE auth.refresh_tokens "
        "SET kiosk_path = regexp_replace(kiosk_path, '/resultados$', '/checkin') "
        "WHERE kiosk_path LIKE '%/resultados'"
    )
    op.execute(
        "ALTER TABLE auth.refresh_tokens ADD CONSTRAINT ck_refresh_tokens_kiosk_path_shape "
        "CHECK (kiosk_path IS NULL OR kiosk_path ~ "
        "'^/clases/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/checkin$')"
    )
