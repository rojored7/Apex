"""Índice por sesión de los resultados vigentes (S8-V7b, M-2 de la revisión final del Sprint 8).

Revision ID: 0041_results_session_index
Revises: 0040_results_void
Create Date: 2026-11-15

`session_has_current_results`, `sessions_with_current_results` y
`member_has_current_result_in_session` filtran `results.wod_results` por `session_id` con la
sesión o la asistencia ya bloqueadas; sin índice recorrían la tabla entera dentro del candado.
`ix_wod_results_session_current ON (session_id, member_id) WHERE is_current AND session_id IS NOT
NULL` cubre las tres. `0040` ya está aplicada en desarrollo: es una migración nueva (S8-D47 deja
de valer). Solo índice, sin datos ni grants. SQL literal.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041_results_session_index"
down_revision: str | None = "0040_results_void"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_wod_results_session_current "
        "ON results.wod_results (session_id, member_id) "
        "WHERE is_current AND session_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX results.ix_wod_results_session_current")
