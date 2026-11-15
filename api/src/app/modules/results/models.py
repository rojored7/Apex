"""Tabla `results.wod_results` (S8-B1, US-169; migraciones `0036` y `0037`; S8-D10, S8-D35, S8-D41).

El resultado de un socio en un WOD. `wod_id`, `member_id` y `session_id` van sin FK entre esquemas.
Las cargas son gramos enteros (`load_g`, S8-D41). `source` (`desk|kiosk`) y las marcas no cambian
nunca; solo `status` (`pending` a `validated`), `is_current` (`true` a `false`) y `updated_at`, y la
base lo hace cumplir (`0037`). Un admin puede anular un resultado vigente y validado (S8-D46 b,
`0040`): `status = voided`, `is_current = false`, con `voided_by`, `voided_at` y `void_reason`, sin
sucesor; un anulado es terminal. Auditada con sujeto `member_id`. No se borra.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.core.db import Base, CommonColumnsMixin

SCHEMA: Final = "results"
UQ_CURRENT: Final = "uq_wod_results_current"
UQ_SUPERSEDES: Final = "uq_wod_results_supersedes"


class WodResult(CommonColumnsMixin, Base):
    __tablename__ = "wod_results"
    __table_args__ = (
        UniqueConstraint("id", "wod_id", "member_id", name="uq_wod_results_id_wod_member"),
        ForeignKeyConstraint(
            ["supersedes_id", "wod_id", "member_id"],
            [
                "results.wod_results.id",
                "results.wod_results.wod_id",
                "results.wod_results.member_id",
            ],
            name="fk_wod_results_supersedes",
        ),
        CheckConstraint("level IN ('rx', 'rx_plus', 'scaled')", name="level"),
        CheckConstraint("status IN ('validated', 'pending', 'voided')", name="status"),
        CheckConstraint("source IN ('desk', 'kiosk')", name="source"),
        CheckConstraint("seconds IS NULL OR seconds BETWEEN 1 AND 86400", name="seconds"),
        CheckConstraint("rounds IS NULL OR rounds BETWEEN 0 AND 1000", name="rounds"),
        CheckConstraint("reps IS NULL OR reps BETWEEN 0 AND 100000", name="reps"),
        CheckConstraint("load_g IS NULL OR load_g BETWEEN 0 AND 1000000", name="load_g"),
        CheckConstraint(
            "NOT capped OR (seconds IS NOT NULL AND reps IS NOT NULL)", name="capped_shape"
        ),
        CheckConstraint(
            "(status IN ('validated', 'voided')) = "
            "(validated_by IS NOT NULL AND validated_at IS NOT NULL)",
            name="validated_pair",
        ),
        CheckConstraint(
            "(status = 'voided') = "
            "(voided_by IS NOT NULL AND voided_at IS NOT NULL AND void_reason IS NOT NULL)",
            name="voided_shape",
        ),
        CheckConstraint(
            "void_reason IS NULL OR char_length(void_reason) BETWEEN 1 AND 200",
            name="void_reason_length",
        ),
        CheckConstraint("status <> 'voided' OR NOT is_current", name="voided_not_current"),
        CheckConstraint("supersedes_id <> id", name="supersedes_not_self"),
        CheckConstraint("cardinality(scaled_movement_ids) <= 30", name="scaled_ids_max"),
        CheckConstraint("scaled_movement_ids = '{}' OR level = 'scaled'", name="scaled_ids_level"),
        Index(UQ_CURRENT, "wod_id", "member_id", unique=True, postgresql_where=text("is_current")),
        Index(
            "ix_wod_results_leaderboard", "wod_id", "status", postgresql_where=text("is_current")
        ),
        Index(
            UQ_SUPERSEDES,
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
        ),
        Index(
            "ix_wod_results_member_date",
            "member_id",
            text("wod_date DESC"),
            postgresql_where=text("is_current"),
        ),
        {"schema": SCHEMA},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    wod_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    member_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    wod_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    benchmark_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    load_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    scaled_movement_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    validated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="desk", server_default=text("'desk'")
    )
    voided_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
