"""`PageParams`, `SearchQuery` y `Page[T]` en una ruta de prueba (US-019 T5)."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import register_error_handlers
from app.core.pagination import Page, PageParams, SearchQuery, to_page


class ItemOut(BaseModel):
    nombre: str


@pytest.fixture
def app() -> FastAPI:
    aplicacion = FastAPI()
    register_error_handlers(aplicacion)

    @aplicacion.get("/items", response_model=Page[ItemOut])
    async def listar(
        params: Annotated[PageParams, Depends()], q: SearchQuery = None
    ) -> Page[ItemOut]:
        items = [
            ItemOut(nombre=f"item-{n}") for n in range(params.offset, params.offset + params.limit)
        ]
        return to_page(items[:3], 3, params)

    return aplicacion


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize("limit", [0, 201, 500])
async def test_limit_fuera_de_rango_da_422_con_field_limit(
    cliente: AsyncClient, limit: int
) -> None:
    async with cliente as c:
        r = await c.get("/items", params={"limit": limit})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "limit"


async def test_offset_negativo_da_422_con_field_offset(cliente: AsyncClient) -> None:
    async with cliente as c:
        r = await c.get("/items", params={"offset": -1})
    assert r.status_code == 422 and r.json()["error"]["field"] == "offset"


async def test_q_de_101_caracteres_da_422_con_field_q(cliente: AsyncClient) -> None:
    async with cliente as c:
        assert (await c.get("/items", params={"q": "a" * 100})).status_code == 200
        r = await c.get("/items", params={"q": "a" * 101})
    assert r.status_code == 422 and r.json()["error"]["field"] == "q"


async def test_la_respuesta_tiene_exactamente_las_cuatro_claves(cliente: AsyncClient) -> None:
    async with cliente as c:
        r = await c.get("/items", params={"limit": 50, "offset": 10})
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert cuerpo["limit"] == 50 and cuerpo["offset"] == 10 and cuerpo["total"] == 3
    assert cuerpo["items"][0] == {"nombre": "item-10"}


def test_page_rechaza_claves_extra() -> None:
    with pytest.raises(ValueError, match="extra"):
        Page[ItemOut](items=[], total=0, limit=25, offset=0, page=1)  # type: ignore[call-arg]
