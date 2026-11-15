"""Movimientos de cada WOD (S8-A3, US-166; S8-D7, S8-D41).

Revision ID: 0035_wods_wod_movements
Revises: 0034_wods_wods
Create Date: 2026-11-15

Tabla `wods.wod_movements`:
- comunes (`id`, `created_at`, `updated_at`, `created_by`);
- `wod_id` (FK a `wods.wods`) y `movement_id` (FK a `wods.movements`);
- `movement_name` (1 a 60): COPIA del nombre al escribir, renombrar el catálogo no cambia un WOD
  pasado (CA3);
- `position` (1 a 30; único por WOD: `uq_wod_movements_wod_position`), `reps` (texto, 0 a 40:
  «21-15-9»), `notes` (0 a 200) e `is_primary` (índice único parcial `uq_wod_movements_primary
  (wod_id) WHERE is_primary`: a lo sumo un principal por WOD, Q19);
- `load_rx_m_g` y `load_rx_f_g`: `integer` NULL, gramos enteros de 0 a 1.000.000 (S8-D41: nada de
  `numeric`; la auditoría canónica rechaza `Decimal`);
- índice `ix_wod_movements_movement_id` (uso de cada movimiento).
`DELETE` SÍ se permite (E6, regla de datos 4): `POST` y `PATCH /wods` reemplazan la lista completa y
el reemplazo queda auditado fila a fila. Sin triggers de guarda. `downgrade`: índices y tabla.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_wods_wod_movements"
down_revision: str | None = "0034_wods_wods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA: Final = "wods"
TABLE: Final = "wod_movements"
UQ_POSITION: Final = "uq_wod_movements_wod_position"
UQ_PRIMARY: Final = "uq_wod_movements_primary"
IX_MOVEMENT: Final = "ix_wod_movements_movement_id"

CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("position", "position BETWEEN 1 AND 30"),
    ("movement_name_length", "char_length(movement_name) BETWEEN 1 AND 60"),
    ("reps_length", "char_length(reps) <= 40"),
    ("notes_length", "char_length(notes) <= 200"),
    ("load_rx_m_g", "load_rx_m_g IS NULL OR load_rx_m_g BETWEEN 0 AND 1000000"),
    ("load_rx_f_g", "load_rx_f_g IS NULL OR load_rx_f_g BETWEEN 0 AND 1000000"),
)


def common_columns() -> list[sa.Column[object]]:
    """Se declara dentro del archivo porque Alembic carga cada revisión por ruta."""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        TABLE,
        *common_columns(),
        sa.Column("wod_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("load_rx_m_g", sa.Integer(), nullable=True),
        sa.Column("load_rx_f_g", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["wod_id"], ["wods.wods.id"], name="fk_wod_movements_wod_id"),
        sa.ForeignKeyConstraint(
            ["movement_id"], ["wods.movements.id"], name="fk_wod_movements_movement_id"
        ),
        *[sa.CheckConstraint(texto, name=nombre) for nombre, texto in CHECKS],
        schema=SCHEMA,
    )
    op.create_index(UQ_POSITION, TABLE, ["wod_id", "position"], unique=True, schema=SCHEMA)
    op.create_index(
        UQ_PRIMARY,
        TABLE,
        ["wod_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_index(IX_MOVEMENT, TABLE, ["movement_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index(IX_MOVEMENT, table_name=TABLE, schema=SCHEMA)
    op.drop_index(UQ_PRIMARY, table_name=TABLE, schema=SCHEMA)
    op.drop_index(UQ_POSITION, table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
