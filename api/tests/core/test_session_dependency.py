"""`get_session`: una transacción por petición; un error revierte y el commit ocurre
antes de responder (US-012, T6 y T11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin, configure_sessionmaker, get_session


class FilaDePeticion(CommonColumnsMixin, Base):
    __tablename__ = "filas_de_peticion"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    nota: Mapped[str] = mapped_column()


@pytest.fixture
async def tabla(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conexion:
        await conexion.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[FilaDePeticion.__table__])
        )
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        configure_sessionmaker(None)
        async with engine.begin() as conexion:
            await conexion.run_sync(
                lambda c: Base.metadata.drop_all(c, tables=[FilaDePeticion.__table__])
            )


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/falla")
    async def falla(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        session.add(FilaDePeticion(nota="no debe quedar", created_by=uuid4()))
        await session.flush()
        raise RuntimeError("falla simulada después de insertar")

    @app.post("/ok")
    async def ok(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        session.add(FilaDePeticion(nota="sí queda", created_by=uuid4()))
        return {"estado": "ok"}

    return app


async def _contar(engine: AsyncEngine) -> int:
    async with engine.connect() as conexion:
        total = await conexion.scalar(select(func.count()).select_from(FilaDePeticion.__table__))
    return int(total or 0)


async def test_una_excepcion_revierte_la_fila(engine: AsyncEngine, tabla: None) -> None:
    transporte = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        respuesta = await cliente.post("/falla")
    assert respuesta.status_code == 500
    assert await _contar(engine) == 0


async def test_el_commit_ocurre_al_responder(engine: AsyncEngine, tabla: None) -> None:
    transporte = ASGITransport(app=_app())
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        respuesta = await cliente.post("/ok")
    assert respuesta.status_code == 200
    assert await _contar(engine) == 1
