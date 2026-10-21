"""Los handlers corren en la misma transacción que el emisor (US-014, T7)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin
from app.core.events import DomainEvent, clear_subscribers, emit, subscribe


class Pedido(CommonColumnsMixin, Base):
    __tablename__ = "pedidos_de_prueba"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    nota: Mapped[str] = mapped_column()
    saldo: Mapped[int] = mapped_column(default=0)


@dataclass(frozen=True, slots=True)
class PedidoCreado(DomainEvent):
    pedido_id: UUID


@pytest.fixture(autouse=True)
async def _tabla(session: AsyncSession) -> None:
    clear_subscribers()
    await session.run_sync(lambda s: Base.metadata.create_all(s.connection(), tables=[Pedido.__table__]))


async def _cuenta(session: AsyncSession) -> int:
    total = await session.scalar(select(func.count()).select_from(Pedido))
    return int(total or 0)


async def test_emisor_y_handler_persisten_juntos(session: AsyncSession) -> None:
    async def acredita(evento: PedidoCreado, s: AsyncSession) -> None:
        await s.execute(update(Pedido).where(Pedido.id == evento.pedido_id).values(saldo=100))

    subscribe(PedidoCreado, acredita)

    async with session.begin_nested():
        pedido = Pedido(nota="a", created_by=uuid4())
        session.add(pedido)
        await session.flush()
        await emit(PedidoCreado(pedido_id=pedido.id), session)

    assert await _cuenta(session) == 1
    assert await session.scalar(select(Pedido.saldo).where(Pedido.id == pedido.id)) == 100


async def test_si_un_handler_falla_se_revierte_todo(session: AsyncSession) -> None:
    async def acredita(evento: PedidoCreado, s: AsyncSession) -> None:
        await s.execute(update(Pedido).where(Pedido.id == evento.pedido_id).values(saldo=100))

    async def falla(evento: PedidoCreado, s: AsyncSession) -> None:
        raise RuntimeError("el segundo handler falla")

    subscribe(PedidoCreado, acredita)
    subscribe(PedidoCreado, falla)

    with pytest.raises(RuntimeError, match="segundo handler"):
        async with session.begin_nested():
            pedido = Pedido(nota="b", created_by=uuid4())
            session.add(pedido)
            await session.flush()
            await emit(PedidoCreado(pedido_id=pedido.id), session)

    assert await _cuenta(session) == 0
