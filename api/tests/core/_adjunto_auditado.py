"""Modelo de prueba de `__audit_exclude__` (S6-C1, S6-D75): imita a `attachments.attachments`."""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin


class AdjuntoAuditado(CommonColumnsMixin, Base):
    __tablename__ = "adjuntos_auditados"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "dueno_id"
    __audit_exclude__: ClassVar[tuple[str, ...]] = ("nombre_azar", "llave")

    dueno_id: Mapped[UUID] = mapped_column()
    tipo: Mapped[str] = mapped_column(default="foto")
    nombre_azar: Mapped[str] = mapped_column(default="0" * 32)
    llave: Mapped[UUID | None] = mapped_column(default=None)
