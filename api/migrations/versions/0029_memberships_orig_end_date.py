"""Fin original de la tiquetera y par de membresía de la asistencia (S7-C2, US-160; S7-D14, S7-D29).

Revision ID: 0029_memberships_orig_end_date
Revises: 0028_attendance
Create Date: 2026-11-14

Dos cambios, en una transacción (Alembic es transaccional en PostgreSQL):
- `memberships.memberships.original_end_date date NULL`: el fin que tenía una tiquetera antes de
  que su última clase la recortara (`end_date = min(end_date, max(start_date, hoy))`, S7-D29).
  `NULL` = no recortada. Sin relleno y sin `NOT NULL` (regla de datos 7: columna nula, llenar,
  obligatoria; aquí nunca se llena: antes de v0.4 nada descontaba, Q4). CHECK
  `ck_memberships_original_end_date_needs_classes`: `original_end_date IS NULL OR classes_total
  IS NOT NULL` (solo las tiqueteras se recortan). Los CHECK de `classes_remaining` ya existen
  desde `0008` (`classes_pair`, `classes_remaining_non_negative`, `classes_remaining_le_total`):
  no se tocan.
- CHECK `ck_attendance_membership_pair` sobre `classes.attendance` (revisión de C1):
  `(membership_status_at_checkin = 'none') = (membership_id IS NULL)`. Sin membresía vigente no
  hay `membership_id`, y con una sí (la que decidió el estado, aunque no descuente). Antes de
  crearlo cuenta las filas que lo violan; si hay alguna aborta con el conteo (no corrige datos).

`downgrade`: quita los dos CHECK y la columna (el fin original recortado se pierde; el volcado
de P-MIG lo conserva). SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

revision: str = "0029_memberships_orig_end_date"
down_revision: str | None = "0028_attendance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNT_VIOLATIONS: Final = (
    "SELECT count(*) FROM classes.attendance "
    "WHERE (membership_status_at_checkin = 'none') IS DISTINCT FROM (membership_id IS NULL)"
)
PAIR_CHECK: Final = "membership_pair"
PAIR_TEXT: Final = "(membership_status_at_checkin = 'none') = (membership_id IS NULL)"
ORIGINAL_CHECK: Final = "original_end_date_needs_classes"
ORIGINAL_TEXT: Final = "original_end_date IS NULL OR classes_total IS NOT NULL"


def upgrade() -> None:
    conexion = op.get_bind()
    malas = conexion.execute(sa.text(COUNT_VIOLATIONS)).scalar_one()
    if malas:
        raise RuntimeError(
            f"0029: {malas} asistencia(s) violan el par membresía/estado; corrígelas antes de migrar"
        )
    op.add_column(
        "memberships",
        sa.Column("original_end_date", sa.Date(), nullable=True),
        schema="memberships",
    )
    op.create_check_constraint(
        ORIGINAL_CHECK, "memberships", ORIGINAL_TEXT, schema="memberships"
    )
    op.create_check_constraint(PAIR_CHECK, "attendance", PAIR_TEXT, schema="classes")


def downgrade() -> None:
    op.drop_constraint(PAIR_CHECK, "attendance", schema="classes", type_="check")
    op.drop_constraint(ORIGINAL_CHECK, "memberships", schema="memberships", type_="check")
    op.drop_column("memberships", "original_end_date", schema="memberships")
