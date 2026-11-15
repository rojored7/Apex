"""CHECK del fin original y guarda de identidad con `original_end_date` (S7-C2b; L2 y L3).

Revision ID: 0030_memberships_end_guard
Revises: 0029_memberships_orig_end_date
Create Date: 2026-11-14

Revisión de seguridad/BD de S7-C2 (`0029` ya está aplicada y no se edita). Dos cambios, en una
transacción:
- CHECK `ck_memberships_original_end_date_after_end` (`original_end_date IS NULL OR
  original_end_date > end_date`, L2): un recorte siempre deja `end_date` ANTES del fin original.
  `0029` solo exigía `classes_total IS NOT NULL` (ese CHECK sigue). [DECISIÓN DE DISEÑO] Es un
  CHECK aparte y no un reemplazo del de `0029`: así `0029` conserva su nombre y su prueba, y el
  `downgrade` solo quita este. Antes de crearlo cuenta las filas que lo violan; si hay alguna
  aborta con el conteo (no corrige datos).
- `memberships.guard_identity()` (L3): `CREATE OR REPLACE` con `original_end_date` entre las
  columnas que no cambian en una fila `cancelled` (una anulada es terminal). El resto del cuerpo
  es el de `0008`; la `CONSTRAINT = memberships_identity` y los triggers (`ENABLE ALWAYS`) no
  cambian.

`downgrade`: quita el CHECK y restaura el cuerpo literal de `0008`. SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op

revision: str = "0030_memberships_end_guard"
down_revision: str | None = "0029_memberships_orig_end_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNT_VIOLATIONS: Final = (
    "SELECT count(*) FROM memberships.memberships "
    "WHERE original_end_date IS NOT NULL AND NOT (original_end_date > end_date)"
)
AFTER_END_CHECK: Final = "original_end_date_after_end"
AFTER_END_TEXT: Final = "original_end_date IS NULL OR original_end_date > end_date"

GUARD_HEAD: Final = """
CREATE OR REPLACE FUNCTION memberships.guard_identity() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.created_by IS DISTINCT FROM OLD.created_by
        OR NEW.member_id IS DISTINCT FROM OLD.member_id
        OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.agreed_price_cop IS DISTINCT FROM OLD.agreed_price_cop
        OR NEW.start_date IS DISTINCT FROM OLD.start_date
        OR NEW.classes_total IS DISTINCT FROM OLD.classes_total
    THEN
        RAISE EXCEPTION 'memberships_identity: la identidad de la membresía no cambia'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'memberships_identity';
    END IF;
    IF OLD.status = 'cancelled' AND (
        NEW.status IS DISTINCT FROM OLD.status
        OR NEW.cancel_reason IS DISTINCT FROM OLD.cancel_reason
        OR NEW.cancelled_by IS DISTINCT FROM OLD.cancelled_by
        OR NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at
        OR NEW.end_date IS DISTINCT FROM OLD.end_date
"""
GUARD_TAIL: Final = """
        OR NEW.classes_remaining IS DISTINCT FROM OLD.classes_remaining
    ) THEN
        RAISE EXCEPTION 'memberships_identity: una membresía anulada no cambia'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'memberships_identity';
    END IF;
    RETURN NEW;
END;
$$
"""
FREEZE_ORIGINAL: Final = "        OR NEW.original_end_date IS DISTINCT FROM OLD.original_end_date\n"
GUARD_WITH_ORIGINAL: Final = GUARD_HEAD + FREEZE_ORIGINAL.rstrip("\n") + GUARD_TAIL
GUARD_0008: Final = GUARD_HEAD.rstrip("\n") + GUARD_TAIL


def upgrade() -> None:
    conexion = op.get_bind()
    malas = conexion.execute(sa.text(COUNT_VIOLATIONS)).scalar_one()
    if malas:
        raise RuntimeError(
            f"0030: {malas} membresía(s) con original_end_date que no es posterior a end_date; "
            "corrígelas antes de migrar"
        )
    op.create_check_constraint(AFTER_END_CHECK, "memberships", AFTER_END_TEXT, schema="memberships")
    op.execute(GUARD_WITH_ORIGINAL)


def downgrade() -> None:
    op.execute(GUARD_0008)
    op.drop_constraint(AFTER_END_CHECK, "memberships", schema="memberships", type_="check")
