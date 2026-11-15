"""Anulación de un resultado por un admin (S8-B3b, S8-D46 b, M-1 de la revisión de B3).

Revision ID: 0040_results_void
Revises: 0039_results_updated_guard
Create Date: 2026-11-15

`results.wod_results` gana `voided_by`, `voided_at` y `void_reason` (nulos) y `status` admite
`voided`. CHECK: `ck_wod_results_status` (tres estados), `ck_wod_results_validated_pair` (un
resultado `validated` o `voided` lleva `validated_by` y `validated_at`; `pending`, ninguno),
`ck_wod_results_voided_shape` (los tres campos de anulación si y solo si `voided`),
`ck_wod_results_void_reason_length` (1 a 200) y `ck_wod_results_voided_not_current`.

Las funciones se reemplazan con `CREATE OR REPLACE` (no se editan `0036` a `0039`):
- `guard_wod_results_insert`: además, una fila nunca nace `voided`.
- `guard_wod_results_update` (cuerpo de `0039` más la anulación): el estado solo pasa de `pending`
  a `validated` o de `validated` a `voided` (solo de una fila vigente, que se apaga en el MISMO
  `UPDATE`); los tres campos de anulación pasan de NULL a valor en esa transición y no se
  reescriben; un anulado es terminal.
- `require_successor`: una fila `voided` apagada no exige sucesor (se anula sin reemplazo).
`downgrade` repone `0039` y quita columnas y CHECK; con filas `voided` el `ADD CONSTRAINT` de
`status` falla y aborta (no se borra ni se reescribe una anulación). SQL literal, sin
interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0040_results_void"
down_revision: str | None = "0039_results_updated_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEAD_UPDATE: Final = (
    "CREATE OR REPLACE FUNCTION results.guard_wod_results_update() RETURNS trigger "
    "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$ "
)
FROZEN: Final = (
    "BEGIN "
    "IF NEW.id IS DISTINCT FROM OLD.id "
    "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
    "OR NEW.created_by IS DISTINCT FROM OLD.created_by "
    "OR NEW.wod_id IS DISTINCT FROM OLD.wod_id "
    "OR NEW.member_id IS DISTINCT FROM OLD.member_id "
    "OR NEW.session_id IS DISTINCT FROM OLD.session_id "
    "OR NEW.wod_date IS DISTINCT FROM OLD.wod_date "
    "OR NEW.benchmark_id IS DISTINCT FROM OLD.benchmark_id "
    "OR NEW.level IS DISTINCT FROM OLD.level "
    "OR NEW.seconds IS DISTINCT FROM OLD.seconds "
    "OR NEW.rounds IS DISTINCT FROM OLD.rounds "
    "OR NEW.reps IS DISTINCT FROM OLD.reps "
    "OR NEW.load_g IS DISTINCT FROM OLD.load_g "
    "OR NEW.capped IS DISTINCT FROM OLD.capped "
    "OR NEW.scaled_movement_ids IS DISTINCT FROM OLD.scaled_movement_ids "
    "OR NEW.recorded_by IS DISTINCT FROM OLD.recorded_by "
    "OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id "
    "OR NEW.source IS DISTINCT FROM OLD.source THEN "
    "RAISE EXCEPTION 'results.wod_results: el resultado registrado no cambia' "
    "USING ERRCODE = 'P0001'; END IF; "
)
VALIDATION: Final = (
    "IF (NEW.validated_by IS DISTINCT FROM OLD.validated_by "
    "OR NEW.validated_at IS DISTINCT FROM OLD.validated_at) "
    "AND NOT (OLD.validated_by IS NULL AND OLD.validated_at IS NULL "
    "AND OLD.status = 'pending' AND NEW.status = 'validated') THEN "
    "RAISE EXCEPTION 'results.wod_results: la validacion no se reescribe' "
    "USING ERRCODE = 'P0001'; END IF; "
    "IF NEW.is_current IS DISTINCT FROM OLD.is_current "
    "AND NOT (OLD.is_current AND NOT NEW.is_current) THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado apagado no vuelve a ser vigente' "
    "USING ERRCODE = 'P0001'; END IF; "
)
NO_BACKWARDS: Final = (
    "IF NEW.updated_at < OLD.updated_at THEN "
    "RAISE EXCEPTION 'results.wod_results: updated_at no retrocede' "
    "USING ERRCODE = 'P0001'; END IF; "
)
STATUS_0039: Final = (
    "IF NEW.status IS DISTINCT FROM OLD.status "
    "AND NOT (OLD.status = 'pending' AND NEW.status = 'validated') THEN "
    "RAISE EXCEPTION 'results.wod_results: el estado solo pasa de pending a validated' "
    "USING ERRCODE = 'P0001'; END IF; "
)
STATUS_0040: Final = (
    "IF NEW.status IS DISTINCT FROM OLD.status "
    "AND NOT (OLD.status = 'pending' AND NEW.status = 'validated') "
    "AND NOT (OLD.status = 'validated' AND NEW.status = 'voided' AND OLD.is_current) THEN "
    "RAISE EXCEPTION 'results.wod_results: transicion de estado no permitida' "
    "USING ERRCODE = 'P0001'; END IF; "
)
VOID_FIELDS: Final = (
    "IF (NEW.voided_by IS DISTINCT FROM OLD.voided_by "
    "OR NEW.voided_at IS DISTINCT FROM OLD.voided_at "
    "OR NEW.void_reason IS DISTINCT FROM OLD.void_reason) "
    "AND NOT (OLD.voided_by IS NULL AND OLD.voided_at IS NULL AND OLD.void_reason IS NULL "
    "AND OLD.status = 'validated' AND NEW.status = 'voided') THEN "
    "RAISE EXCEPTION 'results.wod_results: la anulacion no se reescribe' "
    "USING ERRCODE = 'P0001'; END IF; "
)
UPDATE_0039: Final = (
    HEAD_UPDATE + FROZEN + STATUS_0039 + VALIDATION + NO_BACKWARDS + "RETURN NEW; END; $$"
)
UPDATE_0040: Final = (
    HEAD_UPDATE
    + FROZEN
    + STATUS_0040
    + VALIDATION
    + VOID_FIELDS
    + NO_BACKWARDS
    + "RETURN NEW; END; $$"
)
INSERT_HEAD: Final = (
    "CREATE OR REPLACE FUNCTION results.guard_wod_results_insert() RETURNS trigger "
    "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$ "
)
INSERT_0037: Final = (
    INSERT_HEAD + "BEGIN IF NEW.is_current IS NOT TRUE THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado nuevo nace vigente' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NEW; END; $$"
)
INSERT_0040: Final = (
    INSERT_HEAD + "BEGIN IF NEW.is_current IS NOT TRUE OR NEW.status = 'voided' THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado nuevo nace vigente y no anulado' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NEW; END; $$"
)
SUCCESSOR_HEAD: Final = (
    "CREATE OR REPLACE FUNCTION results.require_successor() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
)
SUCCESSOR_0037: Final = (
    SUCCESSOR_HEAD + "BEGIN IF NEW.is_current IS FALSE AND NOT EXISTS "
    "(SELECT 1 FROM results.wod_results s WHERE s.supersedes_id = NEW.id) THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado apagado exige su sucesor' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NULL; END; $$"
)
SUCCESSOR_0040: Final = (
    SUCCESSOR_HEAD + "BEGIN IF NEW.is_current IS FALSE AND NEW.status <> 'voided' AND NOT EXISTS "
    "(SELECT 1 FROM results.wod_results s WHERE s.supersedes_id = NEW.id) THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado apagado exige su sucesor' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NULL; END; $$"
)

DROP_CHECKS: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results DROP CONSTRAINT ck_wod_results_status",
    "ALTER TABLE results.wod_results DROP CONSTRAINT ck_wod_results_validated_pair",
)
ADD_COLUMNS: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results ADD COLUMN voided_by uuid",
    "ALTER TABLE results.wod_results ADD COLUMN voided_at timestamptz",
    "ALTER TABLE results.wod_results ADD COLUMN void_reason text",
)
ADD_CHECKS_0040: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_status "
    "CHECK (status IN ('validated', 'pending', 'voided'))",
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_validated_pair "
    "CHECK ((status IN ('validated', 'voided')) = "
    "(validated_by IS NOT NULL AND validated_at IS NOT NULL))",
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_voided_shape "
    "CHECK ((status = 'voided') = "
    "(voided_by IS NOT NULL AND voided_at IS NOT NULL AND void_reason IS NOT NULL))",
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_void_reason_length "
    "CHECK (void_reason IS NULL OR char_length(void_reason) BETWEEN 1 AND 200)",
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_voided_not_current "
    "CHECK (status <> 'voided' OR NOT is_current)",
)
ADD_CHECKS_0039: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_status "
    "CHECK (status IN ('validated', 'pending'))",
    "ALTER TABLE results.wod_results ADD CONSTRAINT ck_wod_results_validated_pair "
    "CHECK ((status = 'validated') = (validated_by IS NOT NULL AND validated_at IS NOT NULL))",
)
DROP_NEW_CHECKS: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results DROP CONSTRAINT ck_wod_results_voided_not_current",
    "ALTER TABLE results.wod_results DROP CONSTRAINT ck_wod_results_void_reason_length",
    "ALTER TABLE results.wod_results DROP CONSTRAINT ck_wod_results_voided_shape",
)
DROP_COLUMNS: Final[tuple[str, ...]] = (
    "ALTER TABLE results.wod_results DROP COLUMN void_reason",
    "ALTER TABLE results.wod_results DROP COLUMN voided_at",
    "ALTER TABLE results.wod_results DROP COLUMN voided_by",
)


def upgrade() -> None:
    for sentencia in (*ADD_COLUMNS, *DROP_CHECKS, *ADD_CHECKS_0040):
        op.execute(sentencia)
    for sentencia in (UPDATE_0040, INSERT_0040, SUCCESSOR_0040):
        op.execute(sentencia)


def downgrade() -> None:
    for sentencia in (UPDATE_0039, INSERT_0037, SUCCESSOR_0037):
        op.execute(sentencia)
    op.execute(DROP_NEW_CHECKS[0])
    op.execute(DROP_NEW_CHECKS[1])
    op.execute(DROP_NEW_CHECKS[2])
    for sentencia in DROP_CHECKS:
        op.execute(sentencia)
    for sentencia in ADD_CHECKS_0039:  # falla si hay filas `voided`: no se reescriben
        op.execute(sentencia)
    for sentencia in DROP_COLUMNS:
        op.execute(sentencia)
