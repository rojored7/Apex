"""La guarda de `results.wod_results` exige que `updated_at` no retroceda (S8-B1d, L-9).

Revision ID: 0039_results_updated_guard
Revises: 0038_kiosk_results_path
Create Date: 2026-11-15

`0037` dejaba `updated_at` libre. `CREATE OR REPLACE FUNCTION results.guard_wod_results_update()`
añade `NEW.updated_at < OLD.updated_at` (P0001) antes del `RETURN`; el resto de la guarda es la de
`0037` (no se edita). `downgrade` repone exactamente el cuerpo de `0037`. El trigger, sus
atributos (`ENABLE ALWAYS`) y los grants no cambian. SQL literal, sin interpolación.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0039_results_updated_guard"
down_revision: str | None = "0038_kiosk_results_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BODY_0037: Final = (
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
)
HEAD: Final = (
    "CREATE OR REPLACE FUNCTION results.guard_wod_results_update() RETURNS trigger "
    "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$ "
)
NO_BACKWARDS: Final = (
    "IF NEW.updated_at < OLD.updated_at THEN "
    "RAISE EXCEPTION 'results.wod_results: updated_at no retrocede' "
    "USING ERRCODE = 'P0001'; END IF; "
)


def upgrade() -> None:
    op.execute(HEAD + BODY_0037 + NO_BACKWARDS + "RETURN NEW; END; $$")


def downgrade() -> None:
    op.execute(HEAD + BODY_0037 + "RETURN NEW; END; $$")
