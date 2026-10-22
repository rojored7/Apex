"""Tabla `members.members` (S2-B7, US-069; migración `0006_members`; S2-D16, M-4, M-5).

- Nombres en claro (`first_name`, `last_name`: van al leaderboard), `sex`, `status`,
  `document_type` (`CC` por defecto), `data_consent_at` (lo fija el servidor, M-4) y
  `data_consent_version` (nula en v0.1). Sin `notes` (M-5) y sin columnas `*_hint` (N-02).
- Cifradas por el bus con `aad = id`: `document` (obligatoria), `phone`, `email`, `birth_date`,
  `emergency_contact`. Índices ciegos `document_idx`, `phone_idx`, `email_idx`. El módulo asigna
  siempre `Secret.from_plain(...)`; nunca llama a `bus.encrypt`.
- `__audited__` con `__audit_subject__ = "id"`: la fila de auditoría lleva
  `subject_member_id = id` y los campos cifrados como blob.
- Único parcial `uq_members_document_idx_alive`: un socio dado de baja libera su documento.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import CheckConstraint, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto.secret import Secret
from app.core.crypto.types import BlindIndexed, Encrypted
from app.core.db import Base, CommonColumnsMixin, SoftDeleteMixin

SEXES: tuple[str, ...] = ("f", "m", "x")
STATUSES: tuple[str, ...] = ("active", "inactive")
DOCUMENT_TYPES: tuple[str, ...] = ("CC", "CE", "TI", "PA")
ENCRYPTED_FIELDS: tuple[str, ...] = (
    "document",
    "phone",
    "email",
    "birth_date",
    "emergency_contact",
)


def _blob(columna: str) -> CheckConstraint:
    return CheckConstraint(f"{columna} IS NULL OR {columna} LIKE 'apx1.%'", name=f"{columna}_blob")


class Member(CommonColumnsMixin, SoftDeleteMixin, Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint("sex IN ('f', 'm', 'x')", name="sex"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint("document_type IN ('CC', 'CE', 'TI', 'PA')", name="document_type"),
        CheckConstraint("btrim(first_name) <> ''", name="first_name_not_blank"),
        CheckConstraint("btrim(last_name) <> ''", name="last_name_not_blank"),
        *(_blob(c) for c in ENCRYPTED_FIELDS),
        CheckConstraint("(phone IS NULL) = (phone_idx IS NULL)", name="phone_idx_pair"),
        CheckConstraint("(email IS NULL) = (email_idx IS NULL)", name="email_idx_pair"),
        Index(
            "uq_members_document_idx_alive",
            "document_idx",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_members_phone_idx", "phone_idx"),
        Index("ix_members_email_idx", "email_idx"),
        Index(
            "ix_members_alive_last_name",
            "last_name",
            "first_name",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "members"},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "id"
    # HMAC con llave: en la auditoría permitirían correlacionar socios (revisión S2-B7, MEDIUM-1).
    __audit_redact__: ClassVar[frozenset[str]] = frozenset(
        {"document_idx", "phone_idx", "email_idx"}
    )

    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default=text("'active'")
    )
    document_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="CC", server_default=text("'CC'")
    )
    data_consent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    data_consent_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Secret] = mapped_column(Encrypted("member.document"), nullable=False)
    document_idx: Mapped[str] = mapped_column(
        BlindIndexed("member.document", source="document"), nullable=False
    )
    phone: Mapped[Secret | None] = mapped_column(Encrypted("member.phone"), nullable=True)
    phone_idx: Mapped[str | None] = mapped_column(
        BlindIndexed("member.phone", source="phone"), nullable=True
    )
    email: Mapped[Secret | None] = mapped_column(Encrypted("member.email"), nullable=True)
    email_idx: Mapped[str | None] = mapped_column(
        BlindIndexed("member.email", source="email"), nullable=True
    )
    birth_date: Mapped[Secret | None] = mapped_column(Encrypted("member.birth_date"), nullable=True)
    emergency_contact: Mapped[Secret | None] = mapped_column(
        Encrypted("member.emergency_contact"), nullable=True
    )
