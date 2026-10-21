"""El actor fijado por una dependencia async sigue visible durante el commit del teardown de
`get_session` (US-016 T12). Una dependencia doble imita a `current_user` (US-034): fija
`current_actor` y no lo resetea."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import AuditEntry, install_audit_listeners
from app.core.context import current_actor
from app.core.db import Base, CommonColumnsMixin, configure_sessionmaker, get_session

ACTOR = UUID(int=9)


class NotaAuditada(CommonColumnsMixin, Base):
    __tablename__ = "notas_auditadas_http"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012
    __audited__: ClassVar[bool] = True

    texto: Mapped[str] = mapped_column()


async def _vaciar_auditoria(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE audit.audit_log DISABLE TRIGGER USER"))
        await conn.execute(text("TRUNCATE audit.audit_log"))
        await conn.execute(text("ALTER TABLE audit.audit_log ENABLE TRIGGER USER"))


@pytest.fixture
async def app(engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    install_audit_listeners()
    await _vaciar_auditoria(engine)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[NotaAuditada.__table__]))
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))

    async def usuario_actual() -> UUID:
        current_actor.set(ACTOR)  # como current_user (US-034): fija y no resetea
        return ACTOR

    aplicacion = FastAPI()

    @aplicacion.post("/notas")
    async def crear(
        session: AsyncSession = Depends(get_session),  # noqa: B008
        actor: UUID = Depends(usuario_actual),  # noqa: B008
    ) -> dict[str, str]:
        nota = NotaAuditada(texto="hola")
        session.add(nota)
        return {"id": str(nota.id)}

    token = current_actor.set(None)
    try:
        yield aplicacion
    finally:
        current_actor.reset(token)
        configure_sessionmaker(None)
        await _vaciar_auditoria(engine)
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[NotaAuditada.__table__]))


async def test_el_actor_llega_al_commit_del_teardown(app: FastAPI, engine: AsyncEngine) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
        respuesta = await cliente.post("/notas")
    assert respuesta.status_code == 200
    nota_id = UUID(respuesta.json()["id"])

    async with engine.connect() as conn:
        filas = (await conn.execute(select(AuditEntry.__table__))).mappings().all()
        nota = (await conn.execute(select(NotaAuditada.__table__))).mappings().one()
    assert len(filas) == 1
    assert filas[0]["action"] == "insert"
    assert filas[0]["record_id"] == nota_id
    assert filas[0]["user_id"] == ACTOR
    assert nota["created_by"] == ACTOR
