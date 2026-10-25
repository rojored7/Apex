"""Inmutabilidad de los pagos en la base (S3-B4, US-096; D13, M-6, L-10, S3-D49).

Revision ID: 0011_payments_immutability
Revises: 0010_payments
Create Date: 2026-10-25

Regla de datos 5: un pago nunca se borra ni se edita; un error se corrige anulándolo y
registrando otro. La función `payments.forbid_mutation()` (`plpgsql`, `SECURITY INVOKER`,
`SET search_path = pg_catalog`, sin `EXCEPTION WHEN OTHERS`, L-10) deja pasar una sola
transición: la anulación completa de un pago vigente. Cada rechazo es `RAISE EXCEPTION` con
`ERRCODE = integrity_constraint_violation` (23000), `CONSTRAINT = payments_immutable` y el motivo
en el mensaje (`payments_immutable: <motivo>`), en este orden:
1. `truncate` (vaciar la tabla) y `delete` (borrar una fila), antes de leer `OLD`;
2. `already_voided`: cualquier `UPDATE` sobre un pago anulado (también uno sin cambios);
3. `column`: cambia alguna de las 10 columnas protegidas (`id`, `membership_id`, `member_id`,
   `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by`),
   comparadas con `IS DISTINCT FROM`, aunque la misma sentencia llene las de anulación;
4. `incomplete_void`: el `UPDATE` de un vigente que no deja `voided = true`, motivo visible
   (`btrim` no vacío), `voided_by` y `voided_at`. `updated_at` queda libre.

Triggers `payments_forbid_mutation` (`BEFORE UPDATE OR DELETE ... FOR EACH ROW`) y
`payments_forbid_truncate` (`BEFORE TRUNCATE ... FOR EACH STATEMENT`), los dos con `ENABLE
ALWAYS` (S3-D49, M-6): `session_replication_role = replica` no los salta.

`downgrade`: los dos triggers y la función; no toca filas. Todo el SQL es literal.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0011_payments_immutability"
down_revision: str | None = "0010_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_FORBID_MUTATION: Final = """
CREATE FUNCTION payments.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'payments_immutable: truncate'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'payments_immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'payments_immutable: delete'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'payments_immutable';
    END IF;
    IF OLD.voided THEN
        RAISE EXCEPTION 'payments_immutable: already_voided'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'payments_immutable';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.membership_id IS DISTINCT FROM OLD.membership_id
        OR NEW.member_id IS DISTINCT FROM OLD.member_id
        OR NEW.amount_cop IS DISTINCT FROM OLD.amount_cop
        OR NEW.method IS DISTINCT FROM OLD.method
        OR NEW.reference IS DISTINCT FROM OLD.reference
        OR NEW.paid_at IS DISTINCT FROM OLD.paid_at
        OR NEW.registered_by IS DISTINCT FROM OLD.registered_by
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.created_by IS DISTINCT FROM OLD.created_by
    THEN
        RAISE EXCEPTION 'payments_immutable: column'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'payments_immutable';
    END IF;
    IF NOT (
        NEW.voided IS TRUE
        AND btrim(coalesce(NEW.void_reason, '')) <> ''
        AND NEW.voided_by IS NOT NULL
        AND NEW.voided_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'payments_immutable: incomplete_void'
            USING ERRCODE = 'integrity_constraint_violation',
                  CONSTRAINT = 'payments_immutable';
    END IF;
    RETURN NEW;
END;
$$
"""

CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER payments_forbid_mutation BEFORE UPDATE OR DELETE ON payments.payments "
    "FOR EACH ROW EXECUTE FUNCTION payments.forbid_mutation()",
    "CREATE TRIGGER payments_forbid_truncate BEFORE TRUNCATE ON payments.payments "
    "FOR EACH STATEMENT EXECUTE FUNCTION payments.forbid_mutation()",
)

ENABLE_ALWAYS: Final[tuple[str, ...]] = (
    "ALTER TABLE payments.payments ENABLE ALWAYS TRIGGER payments_forbid_mutation",
    "ALTER TABLE payments.payments ENABLE ALWAYS TRIGGER payments_forbid_truncate",
)

DROP_TRIGGERS: Final[tuple[str, ...]] = (
    "DROP TRIGGER IF EXISTS payments_forbid_truncate ON payments.payments",
    "DROP TRIGGER IF EXISTS payments_forbid_mutation ON payments.payments",
)

DROP_FUNCTION: Final = "DROP FUNCTION IF EXISTS payments.forbid_mutation()"


def upgrade() -> None:
    op.execute(CREATE_FORBID_MUTATION)
    for sentencia in (*CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in (*DROP_TRIGGERS, DROP_FUNCTION):
        op.execute(sentencia)
