"""Inmutabilidad de los resultados (S8-B1, US-169; S8-D35, M-5).

Revision ID: 0037_results_immutability
Revises: 0036_results_wod_results
Create Date: 2026-11-15

Guardas de `results.wod_results` (todas `ENABLE ALWAYS`, `tgenabled = 'A'`):
- `wod_results_guard_insert` (`BEFORE INSERT`): toda fila nace con `is_current = true`;
- `wod_results_guard_update` (`BEFORE UPDATE`): solo cambian `status` (`pending` a `validated`, con
  `validated_by` y `validated_at` pasando de NULL a valor en el MISMO `UPDATE`), `is_current` (solo
  `true` a `false`) y `updated_at`; todo lo demás (incluidos `source`, las marcas y las cargas)
  falla;
- `wod_results_forbid_delete` y `wod_results_forbid_truncate`: los resultados no se borran;
- `wod_results_require_successor` (`CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`): al
  confirmar, toda fila con `is_current = false` tiene un sucesor (otra fila con `supersedes_id`
  igual a su id): una marca no se esconde apagándola.
Las funciones son `SECURITY INVOKER` con `search_path = pg_catalog`.
`downgrade` simétrico: triggers y funciones.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0037_results_immutability"
down_revision: str | None = "0036_results_wod_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS: Final[tuple[str, ...]] = (
    "wod_results_guard_insert",
    "wod_results_guard_update",
    "wod_results_forbid_delete",
    "wod_results_forbid_truncate",
    "wod_results_require_successor",
)

CREATE_FUNCTIONS: Final[tuple[str, ...]] = (
    "CREATE FUNCTION results.guard_wod_results_insert() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN IF NEW.is_current IS NOT TRUE THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado nuevo nace vigente' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NEW; END; $$",
    "CREATE FUNCTION results.guard_wod_results_update() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
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
    "IF NEW.status IS DISTINCT FROM OLD.status "
    "AND NOT (OLD.status = 'pending' AND NEW.status = 'validated') THEN "
    "RAISE EXCEPTION 'results.wod_results: el estado solo pasa de pending a validated' "
    "USING ERRCODE = 'P0001'; END IF; "
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
    "RETURN NEW; END; $$",
    "CREATE FUNCTION results.forbid_mutation() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN RAISE EXCEPTION 'results.% nunca se borran (% prohibido)', "
    "TG_TABLE_NAME, TG_OP USING ERRCODE = 'P0001'; END; $$",
    "CREATE FUNCTION results.require_successor() RETURNS trigger LANGUAGE plpgsql "
    "SECURITY INVOKER SET search_path = pg_catalog AS $$ "
    "BEGIN IF NEW.is_current IS FALSE AND NOT EXISTS "
    "(SELECT 1 FROM results.wod_results s WHERE s.supersedes_id = NEW.id) THEN "
    "RAISE EXCEPTION 'results.wod_results: un resultado apagado exige su sucesor' "
    "USING ERRCODE = 'P0001'; END IF; RETURN NULL; END; $$",
)
CREATE_TRIGGERS: Final[tuple[str, ...]] = (
    "CREATE TRIGGER wod_results_guard_insert BEFORE INSERT ON results.wod_results "
    "FOR EACH ROW EXECUTE FUNCTION results.guard_wod_results_insert()",
    "CREATE TRIGGER wod_results_guard_update BEFORE UPDATE ON results.wod_results "
    "FOR EACH ROW EXECUTE FUNCTION results.guard_wod_results_update()",
    "CREATE TRIGGER wod_results_forbid_delete BEFORE DELETE ON results.wod_results "
    "FOR EACH ROW EXECUTE FUNCTION results.forbid_mutation()",
    "CREATE TRIGGER wod_results_forbid_truncate BEFORE TRUNCATE ON results.wod_results "
    "FOR EACH STATEMENT EXECUTE FUNCTION results.forbid_mutation()",
    "CREATE CONSTRAINT TRIGGER wod_results_require_successor "
    "AFTER INSERT OR UPDATE ON results.wod_results DEFERRABLE INITIALLY DEFERRED "
    "FOR EACH ROW EXECUTE FUNCTION results.require_successor()",
)
ENABLE_ALWAYS: Final[tuple[str, ...]] = tuple(
    f"ALTER TABLE results.wod_results ENABLE ALWAYS TRIGGER {nombre}" for nombre in TRIGGERS
)
DROP_FUNCTIONS: Final[tuple[str, ...]] = (
    "DROP FUNCTION IF EXISTS results.require_successor()",
    "DROP FUNCTION IF EXISTS results.forbid_mutation()",
    "DROP FUNCTION IF EXISTS results.guard_wod_results_update()",
    "DROP FUNCTION IF EXISTS results.guard_wod_results_insert()",
)


def upgrade() -> None:
    for sentencia in (*CREATE_FUNCTIONS, *CREATE_TRIGGERS, *ENABLE_ALWAYS):
        op.execute(sentencia)


def downgrade() -> None:
    for nombre in reversed(TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {nombre} ON results.wod_results")
    for sentencia in DROP_FUNCTIONS:
        op.execute(sentencia)
