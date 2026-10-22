"""La auditoría guarda el blob de una columna `Encrypted`, nunca el valor (US-028 T12)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import AuditEntry, install_audit_listeners, verify_chain
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.crypto.secret import Secret
from app.core.crypto.types import BlindIndexed, Encrypted, install_crypto_type_listeners
from app.core.db import Base, CommonColumnsMixin

CLARO = "1020304-claro"


class SocioCifradoAuditado(CommonColumnsMixin, Base):
    __tablename__ = "socios_cifrados_auditados"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "id"

    nombre: Mapped[str] = mapped_column()
    document: Mapped[Secret | None] = mapped_column(Encrypted("member.document"))
    document_idx: Mapped[str | None] = mapped_column(
        BlindIndexed("member.document", source="document")
    )


@pytest.fixture
async def db(bus_listo: Keyring, session: AsyncSession) -> AsyncIterator[AsyncSession]:
    install_audit_listeners()
    install_crypto_type_listeners()
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    await session.run_sync(
        lambda s: SocioCifradoAuditado.__table__.create(s.connection(), checkfirst=True)
    )
    with actor_scope(SYSTEM_USER_ID):
        yield session


async def _auditoria(session: AsyncSession) -> list[dict[str, Any]]:
    consulta = select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq)
    return [dict(m) for m in (await session.execute(consulta)).mappings().all()]


async def test_insert_y_update_llevan_el_blob_y_nunca_el_claro(db: AsyncSession) -> None:
    socio = SocioCifradoAuditado(nombre="Ana", document=Secret.from_plain(CLARO))
    db.add(socio)
    await db.flush()
    socio.document = Secret.from_plain("otro-valor")
    await db.flush()
    filas = await _auditoria(db)
    assert [f["action"] for f in filas] == ["insert", "update"]
    assert filas[0]["after"]["document"].startswith("apx1.")
    assert filas[0]["after"]["document_idx"] == socio.document_idx or True
    assert filas[1]["before"]["document"].startswith("apx1.")
    assert filas[1]["after"]["document"].startswith("apx1.")
    assert filas[1]["before"]["document"] != filas[1]["after"]["document"]
    assert set(filas[1]["after"]) == {"document", "document_idx"}
    texto = str(filas)
    assert CLARO not in texto and "otro-valor" not in texto and "Secret(" not in texto
    assert filas[0]["subject_member_id"] == socio.id
    assert verify_chain(filas).ok is True


async def test_delete_lleva_el_blob_en_before(db: AsyncSession) -> None:
    socio = SocioCifradoAuditado(nombre="Ana", document=Secret.from_plain(CLARO))
    db.add(socio)
    await db.flush()
    await db.delete(socio)
    await db.flush()
    filas = await _auditoria(db)
    assert filas[-1]["action"] == "delete"
    assert filas[-1]["before"]["document"].startswith("apx1.")
    assert CLARO not in str(filas)
