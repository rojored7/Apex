"""`paginate` con PostgreSQL real (US-019 T4): total, orden estable y páginas sin huecos."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import Base, CommonColumnsMixin
from app.core.pagination import DEFAULT_LIMIT, PageParams, paginate, to_page

N = 30


class FilaPaginada(CommonColumnsMixin, Base):
    __tablename__ = "filas_paginadas"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    grupo: Mapped[int] = mapped_column()
    nombre: Mapped[str] = mapped_column()


@pytest.fixture
async def filas(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    await session.run_sync(
        lambda s: Base.metadata.create_all(s.connection(), tables=[FilaPaginada.__table__])
    )
    with actor_scope(SYSTEM_USER_ID):
        # Diez grupos de tres filas: el orden por `grupo` empata a propósito.
        session.add_all(FilaPaginada(grupo=n % 10, nombre=f"fila-{n:02d}") for n in range(N))
        await session.flush()
    yield session


async def test_sin_parametros_da_25_items_y_total_30(filas: AsyncSession) -> None:
    items, total = await paginate(filas, select(FilaPaginada), PageParams())
    assert len(items) == DEFAULT_LIMIT and total == N
    page = to_page(items, total, PageParams())
    assert page.model_dump(include={"total", "limit", "offset"}) == {
        "total": N,
        "limit": DEFAULT_LIMIT,
        "offset": 0,
    }
    assert len(page.items) == DEFAULT_LIMIT


async def test_las_paginas_cubren_todo_sin_repetidos_aunque_el_orden_empate(
    filas: AsyncSession,
) -> None:
    stmt = select(FilaPaginada).order_by(FilaPaginada.grupo)
    vistos: list[UUID] = []
    for offset in (0, 7, 14, 21, 28):
        items, total = await paginate(filas, stmt, PageParams(limit=7, offset=offset))
        assert total == N
        vistos.extend(f.id for f in items)
    assert len(vistos) == N
    assert len(set(vistos)) == N
    grupos = [f.grupo for f in (await paginate(filas, stmt, PageParams(limit=N)))[0]]
    assert grupos == sorted(grupos)


async def test_total_respeta_el_filtro_y_no_depende_de_la_pagina(filas: AsyncSession) -> None:
    stmt = select(FilaPaginada).where(FilaPaginada.grupo < 4)
    items_a, total_a = await paginate(filas, stmt, PageParams(limit=5, offset=0))
    items_b, total_b = await paginate(filas, stmt, PageParams(limit=5, offset=10))
    assert total_a == total_b == 12
    assert len(items_a) == 5 and len(items_b) == 2


async def test_un_select_sin_order_by_queda_ordenado_por_id(filas: AsyncSession) -> None:
    items, _ = await paginate(filas, select(FilaPaginada), PageParams(limit=N))
    ids = [f.id for f in items]
    assert ids == sorted(ids)


async def test_offset_mas_alla_del_final_da_lista_vacia(filas: AsyncSession) -> None:
    items, total = await paginate(filas, select(FilaPaginada), PageParams(limit=10, offset=100))
    assert items == [] and total == N
