"""Petición completa: un handler que falla revierte la fila del emisor (US-014, T8)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin, configure_sessionmaker, get_session
from app.core.errors import register_error_handlers
from app.core.events import DomainEvent, clear_subscribers, emit, subscribe


class Venta(CommonColumnsMixin, Base):
    __tablename__ = "ventas_de_prueba"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    nota: Mapped[str] = mapped_column()


@dataclass(frozen=True, slots=True)
class VentaHecha(DomainEvent):
    venta_id: UUID


@pytest.fixture
async def tabla(engine: AsyncEngine, restaurar_bus: None) -> AsyncIterator[None]:
    clear_subscribers()  # bus vacío solo en esta prueba; `restaurar_bus` lo devuelve (E7)
    async with engine.begin() as c:
        await c.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[Venta.__table__]))
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        configure_sessionmaker(None)
        async with engine.begin() as c:
            await c.run_sync(lambda conn: Base.metadata.drop_all(conn, tables=[Venta.__table__]))


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/ventas")
    async def vender(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        venta = Venta(nota="x", created_by=uuid4())
        session.add(venta)
        await session.flush()
        await emit(VentaHecha(venta_id=venta.id), session)
        return {"id": str(venta.id)}

    return app


async def test_handler_que_falla_responde_error_y_no_deja_fila(
    engine: AsyncEngine, tabla: None
) -> None:
    async def falla(evento: VentaHecha, s: AsyncSession) -> None:
        raise RuntimeError("activar membresía falló")

    subscribe(VentaHecha, falla)
    transporte = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as c:
        r = await c.post("/ventas")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    async with engine.connect() as conexion:
        total = await conexion.scalar(select(func.count()).select_from(Venta.__table__))
    assert total == 0


async def test_handler_en_verde_deja_la_fila(engine: AsyncEngine, tabla: None) -> None:
    vistos: list[UUID] = []

    async def registra(evento: VentaHecha, s: AsyncSession) -> None:
        vistos.append(evento.venta_id)

    subscribe(VentaHecha, registra)
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://pruebas") as c:
        r = await c.post("/ventas")
    assert r.status_code == 200
    assert vistos == [UUID(r.json()["id"])]
    async with engine.connect() as conexion:
        total = await conexion.scalar(select(func.count()).select_from(Venta.__table__))
    assert total == 1
