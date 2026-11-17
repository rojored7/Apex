"""Tabla `athletes.body_metrics` (S9-A1, US-178; migración `0042`; S9-D3, S9-D4, S9-D31, S9-D32).

- En claro: `member_id` (sin FK entre esquemas), `measured_on` (fecha civil de Bogotá),
  `recorded_by` y `voided_at` / `voided_by` (anulación, S9-D13).
- Cifradas por el bus con `aad = id` y la clase `athlete.metric`: `weight_g`, `height_cm`,
  `body_fat_pct` y `notes`. El módulo asigna siempre `Secret.from_plain(...)` con el claro de
  `rules.encode_metric`; nunca llama a `bus.encrypt`.
- `__audited__`: la auditoría guarda el blob, nunca el valor. Sujeto: `member_id`.
- CHECK, índice y guardas de la base: ver la migración `0042` (no se repiten aquí).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    FetchedValue,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.core.crypto.secret import Secret
from app.core.crypto.types import Encrypted
from app.core.db import Base, CommonColumnsMixin

SCHEMA: Final = "athletes"
ENCRYPTED_FIELDS: Final[tuple[str, ...]] = ("weight_g", "height_cm", "body_fat_pct", "notes")
DATA_CLASS: Final = "athlete.metric"


class BodyMetric(CommonColumnsMixin, Base):
    __tablename__ = "body_metrics"
    __table_args__ = (
        CheckConstraint(
            "weight_g IS NOT NULL OR height_cm IS NOT NULL OR body_fat_pct IS NOT NULL",
            name="at_least_one_measure",
        ),
        CheckConstraint("(voided_at IS NULL) = (voided_by IS NULL)", name="voided_pair"),
        Index(
            "ix_body_metrics_member_date",
            "member_id",
            text("measured_on DESC"),
            text("created_at DESC"),
        ),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    member_id: Mapped[UUID] = mapped_column(nullable=False)
    measured_on: Mapped[date_type] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[UUID] = mapped_column(nullable=False)
    weight_g: Mapped[Secret | None] = mapped_column(Encrypted(DATA_CLASS), nullable=True)
    height_cm: Mapped[Secret | None] = mapped_column(Encrypted(DATA_CLASS), nullable=True)
    body_fat_pct: Mapped[Secret | None] = mapped_column(Encrypted(DATA_CLASS), nullable=True)
    notes: Mapped[Secret | None] = mapped_column(Encrypted(DATA_CLASS), nullable=True)
    # `FetchedValue`: el INSERT los omite (el api no tiene INSERT sobre `voided_*`, S9-D31); solo
    # los escribe la anulación por UPDATE (patrón de `payments.payments`).
    voided_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, server_default=FetchedValue()
    )
    voided_by: Mapped[UUID | None] = mapped_column(nullable=True, server_default=FetchedValue())


RECORD_CHECKS: Final[tuple[tuple[str, str], ...]] = (
    ("kind", "kind IN ('rm', 'benchmark')"),
    ("source", "source IN ('manual', 'derived')"),
    ("level", "level IS NULL OR level IN ('rx', 'rx_plus', 'scaled')"),
    ("value_g", "value_g IS NULL OR value_g BETWEEN 1 AND 1000000"),
    ("seconds", "seconds IS NULL OR seconds BETWEEN 1 AND 86400"),
    ("rounds", "rounds IS NULL OR rounds BETWEEN 0 AND 1000"),
    ("reps", "reps IS NULL OR reps BETWEEN 0 AND 100000"),
    ("load_g", "load_g IS NULL OR load_g BETWEEN 0 AND 1000000"),
    ("capped_shape", "NOT capped OR (seconds IS NOT NULL AND reps IS NOT NULL)"),
    (
        "rm_shape",
        "kind <> 'rm' OR (movement_id IS NOT NULL AND value_g IS NOT NULL "
        "AND benchmark_id IS NULL AND level IS NULL AND seconds IS NULL AND rounds IS NULL "
        "AND reps IS NULL AND load_g IS NULL)",
    ),
    (
        "benchmark_shape",
        "kind <> 'benchmark' OR (benchmark_id IS NOT NULL AND level IS NOT NULL "
        "AND movement_id IS NULL AND value_g IS NULL "
        "AND num_nonnulls(seconds, rounds, reps, load_g) >= 1)",
    ),
    ("derived_shape", "source <> 'derived' OR (result_id IS NOT NULL AND wod_id IS NOT NULL)"),
    ("manual_shape", "source <> 'manual' OR (result_id IS NULL AND wod_id IS NULL)"),
    ("capped_manual", "source <> 'manual' OR NOT capped"),
    ("invalidated_pair", "(invalidated_at IS NULL) = (invalidated_reason IS NULL)"),
    ("invalidated_by_pair", "(invalidated_at IS NULL) = (invalidated_by IS NULL)"),
    (
        "invalidated_result_superseded",
        "invalidated_by_result_id IS NULL OR invalidated_reason = 'superseded'",
    ),
    ("invalidated_after_created", "invalidated_at IS NULL OR invalidated_at >= created_at"),
    ("updated_after_created", "updated_at >= created_at"),
    (
        "invalidated_reason_source",
        "invalidated_reason IS NULL "
        "OR (invalidated_reason = 'manual_error' AND source = 'manual') "
        "OR (invalidated_reason IN ('superseded', 'voided') AND source = 'derived')",
    ),
)


class PersonalRecord(CommonColumnsMixin, Base):
    """Tabla `athletes.personal_records` (S9-B1, US-180; migración `0043`; S9-D8, S9-D31).

    CHECK de forma e índices iguales a los de la migración `0043` (los espeja el modelo para que
    `create_all` de las pruebas y Alembic no difieran). Un récord no es dato de salud: ninguna
    columna se cifra. `invalidated_*` los escribe solo la invalidación por UPDATE (el api no tiene
    `INSERT` sobre ellas, S9-D31): `FetchedValue` las omite del INSERT. Las guardas, el único
    `(result_id, kind)` y los índices parciales con la columna desnuda `invalidated_at IS NULL`
    (S8-D50) viven en la migración.
    """

    __tablename__ = "personal_records"
    __table_args__ = (
        *(CheckConstraint(texto, name=nombre) for nombre, texto in RECORD_CHECKS),
        Index(
            "uq_personal_records_result_kind",
            "result_id",
            "kind",
            unique=True,
            postgresql_where=text("result_id IS NOT NULL"),
        ),
        Index(
            "ix_personal_records_rm",
            "member_id",
            "movement_id",
            postgresql_where=text("kind = 'rm' AND invalidated_at IS NULL"),
        ),
        Index(
            "ix_personal_records_bench",
            "member_id",
            "benchmark_id",
            postgresql_where=text("kind = 'benchmark' AND invalidated_at IS NULL"),
        ),
        Index(
            "ix_personal_records_member_date",
            "member_id",
            text("achieved_on DESC"),
            text("created_at DESC"),
        ),
        Index(
            "ix_personal_records_movement",
            "movement_id",
            postgresql_where=text("movement_id IS NOT NULL"),
        ),
        Index(
            "ix_personal_records_benchmark",
            "benchmark_id",
            postgresql_where=text("benchmark_id IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    # `clock_timestamp()` (S9-D52): el instante real del INSERT, no el inicio de la transacción.
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp(), nullable=False
    )
    member_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    movement_id: Mapped[UUID | None] = mapped_column(nullable=True)
    benchmark_id: Mapped[UUID | None] = mapped_column(nullable=True)
    wod_id: Mapped[UUID | None] = mapped_column(nullable=True)
    value_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    load_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    achieved_on: Mapped[date_type] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    result_id: Mapped[UUID | None] = mapped_column(nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, server_default=FetchedValue()
    )
    invalidated_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default=FetchedValue()
    )
    invalidated_by: Mapped[UUID | None] = mapped_column(
        nullable=True, server_default=FetchedValue()
    )
    invalidated_by_result_id: Mapped[UUID | None] = mapped_column(
        nullable=True, server_default=FetchedValue()
    )
