"""Texto en claro hacia una columna cifrada: el flush se rechaza antes de auditar (US-016 T10)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import AuditEntry, PlaintextInAuditError, install_audit_listeners
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.secret import Secret
from app.core.crypto.types import Encrypted, install_crypto_type_listeners
from app.core.db import Base, CommonColumnsMixin
from tests.crypto.conftest import bus_listo, proveedor_local, sin_llaves  # noqa: F401


class NotaCifrada(CommonColumnsMixin, Base):
    __tablename__ = "notas_cifradas_auditadas"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True

    phone: Mapped[Secret | None] = mapped_column(Encrypted("member.phone"))


@pytest.fixture
async def db(bus_listo: Keyring, session: AsyncSession) -> AsyncIterator[AsyncSession]:  # noqa: F811
    install_audit_listeners()
    install_crypto_type_listeners()
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    await session.run_sync(lambda s: NotaCifrada.__table__.create(s.connection(), checkfirst=True))
    with actor_scope(SYSTEM_USER_ID):
        yield session


async def test_texto_en_claro_rompe_el_flush_sin_dejar_auditoria(db: AsyncSession) -> None:
    db.add(NotaCifrada(phone="3001234567"))  # type: ignore[arg-type]
    with pytest.raises((CryptoError, PlaintextInAuditError)):
        await db.flush()
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(AuditEntry)) == 0


async def test_el_secret_entra_como_blob(db: AsyncSession) -> None:
    nota = NotaCifrada(phone=Secret.from_plain("3001234567"))
    db.add(nota)
    await db.flush()
    fila = (await db.execute(select(AuditEntry.__table__))).mappings().one()
    assert fila["after"]["phone"].startswith("apx1.") and "3001234567" not in str(fila["after"])
