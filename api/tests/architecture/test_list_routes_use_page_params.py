"""Toda lista `GET` pagina con `PageParams` y acepta `q` (US-019 T6, criterio 5; regla de datos
6; S2-D3 endurecida en S2-B3).

S2-D3: los routers son planos y FastAPI los incluye de forma perezosa, así que se recorren las
rutas EFECTIVAS de `create_app(...)` (`effective_routes`) y no `router.routes`. Para cada `GET`
publicado se lee su contrato en `app.openapi()`:
- una respuesta `Page_...` exige la dependencia `PageParams`, un parámetro de query `q` y
  `limit` con máximo 200 (`MAX_LIMIT`);
- ninguna respuesta 200 de un `GET` es un arreglo suelto (toda lista pagina en el servidor).
Los controles construyen apps desechables que deben fallar.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from pydantic import BaseModel

from app.core.config import Settings
from app.core.pagination import MAX_LIMIT, Page, PageParams, SearchQuery
from app.core.security import effective_routes
from app.main import create_app

SCHEMA_REF = "#/components/schemas/"


def _usa_page_params(dependant: Dependant) -> bool:
    return any(d.call is PageParams or _usa_page_params(d) for d in dependant.dependencies)


def _query_params(dependant: Dependant) -> set[str]:
    nombres = {p.alias or p.name for p in dependant.query_params}
    for dep in dependant.dependencies:
        nombres |= _query_params(dep)
    return nombres


def _respuesta_200(operacion: dict[str, Any]) -> dict[str, Any]:
    contenido = operacion.get("responses", {}).get("200", {}).get("content", {})
    schema: dict[str, Any] = contenido.get("application/json", {}).get("schema", {})
    return schema


def _limite_maximo(operacion: dict[str, Any]) -> Any:
    for parametro in operacion.get("parameters", []):
        if parametro.get("in") == "query" and parametro.get("name") == "limit":
            return parametro.get("schema", {}).get("maximum")
    return None


def problemas_de_listas(app: FastAPI) -> tuple[list[str], list[str]]:
    """`(problemas, listas)`: qué lista `GET` incumple y cuáles se revisaron."""
    esquema = app.openapi()
    problemas: list[str] = []
    listas: list[str] = []
    for ruta in effective_routes(app)[0]:
        if "GET" not in ruta.methods:
            continue
        operacion = esquema.get("paths", {}).get(ruta.path, {}).get("get")
        if operacion is None:
            continue
        respuesta = _respuesta_200(operacion)
        if respuesta.get("type") == "array":
            problemas.append(f"GET {ruta.path}: devuelve un arreglo sin paginar")
            continue
        ref = str(respuesta.get("$ref", ""))
        if not ref.removeprefix(SCHEMA_REF).startswith("Page_"):
            continue
        listas.append(f"GET {ruta.path}")
        if not _usa_page_params(ruta.dependant):
            problemas.append(f"GET {ruta.path}: sin PageParams")
        if "q" not in _query_params(ruta.dependant):
            problemas.append(f"GET {ruta.path}: sin q")
        if _limite_maximo(operacion) != MAX_LIMIT:
            problemas.append(f"GET {ruta.path}: limit sin máximo {MAX_LIMIT}")
    return problemas, listas


def test_las_listas_efectivas_de_la_app_paginan_y_aceptan_q(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == [], "\n".join(problemas)
    # S2-B3 publica la primera lista paginada (`GET /users`); el recorrido no puede quedar vacío.
    # S2-B8 agrega `GET /members` y S2-B9 `GET /plans`: las tres deben recogerse.
    assert {"GET /api/v1/users", "GET /api/v1/members", "GET /api/v1/plans"} <= set(listas)


class _Out(BaseModel):
    x: int


def _app_de_control() -> FastAPI:
    router = APIRouter()

    @router.get("/sin", response_model=Page[_Out])
    async def sin(q: SearchQuery = None) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=25, offset=0)

    @router.get("/sin-q", response_model=Page[_Out])
    async def sin_q(params: Annotated[PageParams, Depends()]) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/con", response_model=Page[_Out])
    async def con(params: Annotated[PageParams, Depends()], q: SearchQuery = None) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/arreglo", response_model=list[_Out])
    async def arreglo() -> list[_Out]:
        return []

    @router.get("/uno", response_model=_Out)
    async def uno() -> _Out:
        return _Out(x=1)

    app = FastAPI()
    padre = APIRouter(prefix="/api/v1")
    padre.include_router(router)  # incluido como los módulos: perezoso
    app.include_router(padre)
    return app


def test_el_control_detecta_listas_sin_page_params_sin_q_y_arreglos() -> None:
    problemas, listas = problemas_de_listas(_app_de_control())
    assert sorted(problemas) == [
        "GET /api/v1/arreglo: devuelve un arreglo sin paginar",
        "GET /api/v1/sin-q: sin q",
        "GET /api/v1/sin: limit sin máximo 200",
        "GET /api/v1/sin: sin PageParams",
    ]
    assert sorted(listas) == ["GET /api/v1/con", "GET /api/v1/sin", "GET /api/v1/sin-q"]
