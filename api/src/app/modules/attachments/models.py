"""Tabla `attachments.attachments` (S6-C1; migración `0023_attachments`; S6-D25, S6-D75). Stub."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin


class Attachment(CommonColumnsMixin, Base):
    __tablename__ = "attachments"
    # La FK `fk_attachments_key_id` (0025) vive solo en la migración (E2: sin resolver `crypto`).
    __table_args__ = (
        CheckConstraint("kind <> 'photo' OR NOT sensitive", name="photo_not_sensitive"),
        {"schema": "attachments"},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "owner_id"
    # L-1 (S6-D75): con S3 `filename_random` es la clave del objeto y `key_id` identifica la llave.
    __audit_exclude__: ClassVar[tuple[str, ...]] = ("filename_random", "key_id")

    owner_table: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    filename_random: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    key_id: Mapped[UUID | None] = mapped_column(nullable=True)
    storage_provider: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(nullable=False)
