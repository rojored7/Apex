"""Modelo de prueba con los cinco `Encrypted` y los tres `BlindIndexed` de v0.1 (US-028 T1)."""

from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto.secret import Secret
from app.core.crypto.types import BlindIndexed, Encrypted
from app.core.db import Base, CommonColumnsMixin

SCHEMA = "test_crypto"


class CryptoTestPerson(CommonColumnsMixin, Base):
    __tablename__ = "crypto_test_person"
    __table_args__ = (
        Index("ix_crypto_test_person_document_idx", "document_idx"),
        {"schema": SCHEMA},
    )

    name: Mapped[str] = mapped_column()
    document: Mapped[Secret | None] = mapped_column(Encrypted("member.document"))
    document_idx: Mapped[str | None] = mapped_column(
        BlindIndexed("member.document", source="document")
    )
    phone: Mapped[Secret | None] = mapped_column(Encrypted("member.phone"))
    phone_idx: Mapped[str | None] = mapped_column(BlindIndexed("member.phone", source="phone"))
    email: Mapped[Secret | None] = mapped_column(Encrypted("member.email"))
    email_idx: Mapped[str | None] = mapped_column(BlindIndexed("member.email", source="email"))
    birth_date: Mapped[Secret | None] = mapped_column(Encrypted("member.birth_date"))
    emergency_contact: Mapped[Secret | None] = mapped_column(Encrypted("member.emergency_contact"))
