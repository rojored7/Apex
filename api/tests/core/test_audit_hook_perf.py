"""500 inserciones auditadas en una transacción en menos de 5 s (US-016 T11; insumo de US-112)."""

from __future__ import annotations

import time
from typing import ClassVar

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import AuditEntry, install_audit_listeners, verify_chain
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import Base, CommonColumnsMixin

LIMITE_S = 5.0
N = 500


class FilaDeLote(CommonColumnsMixin, Base):
    __tablename__ = "filas_de_lote"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True

    valor: Mapped[int] = mapped_column()


async def test_500_inserciones_auditadas_en_menos_de_5_s(session: AsyncSession) -> None:
    install_audit_listeners()
    await session.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
    await session.execute(text("TRUNCATE audit.audit_log"))
    await session.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))
    await session.run_sync(
        lambda s: Base.metadata.create_all(s.connection(), tables=[FilaDeLote.__table__])
    )
    inicio = time.perf_counter()
    with actor_scope(SYSTEM_USER_ID):
        session.add_all(FilaDeLote(valor=n) for n in range(N))
        await session.flush()
    duracion = time.perf_counter() - inicio
    total = await session.scalar(select(func.count()).select_from(AuditEntry))
    assert total == N
    filas = (
        await session.execute(select(AuditEntry.__table__).order_by(AuditEntry.__table__.c.seq))
    ).mappings().all()
    assert verify_chain([dict(f) for f in filas]).ok is True
    assert duracion < LIMITE_S, f"{N} inserciones auditadas tardaron {duracion:.2f} s"
