"""Toda ruta GET que responde `Page[...]` declara `PageParams` (US-019 T6, criterio 5).

Recorre los routers de `MODULES` (FastAPI incluye los routers de forma perezosa, así que
se leen directamente) y un router de control que debe fallar.
"""

from __future__ import annotations

import importlib
from typing import Annotated, get_origin

from fastapi import APIRouter, Depends
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core.pagination import Page, PageParams
from app.main import MODULES


def _usa_page_params(dependant: Dependant) -> bool:
    return any(d.call is PageParams or _usa_page_params(d) for d in dependant.dependencies)


def routes_missing_page_params(router: APIRouter) -> list[str]:
    faltan: list[str] = []
    for route in router.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        modelo = route.response_model
        # `Page[X]` de Pydantic es una subclase parametrizada de `Page`, no un alias de typing.
        es_page = get_origin(modelo) is Page or (
            isinstance(modelo, type) and issubclass(modelo, Page)
        )
        if not es_page:
            continue
        if not _usa_page_params(route.dependant):
            faltan.append(f"GET {route.path}")
    return faltan


def _routers_de_modulos() -> list[tuple[str, APIRouter]]:
    salida: list[tuple[str, APIRouter]] = []
    for nombre in MODULES:
        modulo = importlib.import_module(f"app.modules.{nombre}.router")
        salida.append((nombre, modulo.router))
    return salida


def test_las_listas_de_los_modulos_usan_page_params() -> None:
    faltan = [
        f"{nombre}: {ruta}"
        for nombre, router in _routers_de_modulos()
        for ruta in routes_missing_page_params(router)
    ]
    assert faltan == []


class _Out(BaseModel):
    x: int


def test_el_control_detecta_una_lista_sin_page_params() -> None:
    router = APIRouter()

    @router.get("/sin", response_model=Page[_Out])
    async def sin() -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=25, offset=0)

    @router.get("/con", response_model=Page[_Out])
    async def con(params: Annotated[PageParams, Depends()]) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/uno", response_model=_Out)
    async def uno() -> _Out:
        return _Out(x=1)

    assert routes_missing_page_params(router) == ["GET /sin"]
