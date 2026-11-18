"""CHECK de orden temporal en `athletes.body_metrics` (S9-V7b, L1 de la revisión V7).

Revision ID: 0044_body_metrics_time_checks
Revises: 0043_athletes_personal_records
Create Date: 2026-11-18

Dos CHECK, iguales a los de `0043` en `athletes.personal_records`:
- `voided_after_created`: `voided_at IS NULL OR voided_at >= created_at`;
- `updated_after_created`: `updated_at >= created_at`.
`void_metric` ya toma `voided_at` de `clock_timestamp()` de la base (S9-D52): un reloj de la
aplicación atrasado no puede dejar una anulación anterior a la medición. La tabla de desarrollo
se comprobó ANTES de aplicar (consulta de solo lectura: ninguna fila viola los dos CHECK); si
alguna violara, `ADD CONSTRAINT` fallaría y no cambiaría nada (DDL transaccional).

`downgrade`: quita los dos CHECK; no toca filas. SQL literal, sin interpolación de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0044_body_metrics_time_checks"
down_revision: str | None = "0043_athletes_personal_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "athletes"
TABLE: Final = "body_metrics"
CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("ck_body_metrics_voided_after_created", "voided_at IS NULL OR voided_at >= created_at"),
    ("ck_body_metrics_updated_after_created", "updated_at >= created_at"),
)


def upgrade() -> None:
    for nombre, condicion in CHECKS:
        op.create_check_constraint(op.f(nombre), TABLE, condicion, schema=SCHEMA)


def downgrade() -> None:
    for nombre, _ in reversed(CHECKS):
        op.drop_constraint(op.f(nombre), TABLE, schema=SCHEMA, type_="check")
