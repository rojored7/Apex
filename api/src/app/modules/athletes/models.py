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

from sqlalchemy import CheckConstraint, Date, FetchedValue, Index, text
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
