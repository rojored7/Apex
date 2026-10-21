"""`route_has_role_dependency` y `unprotected_routes` con apps sintéticas (US-035 T4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from app.core.security import (
    Principal,
    RouteInfo,
    effective_routes,
    require_role,
    route_has_role_dependency,
    unprotected_routes,
)


def _ruta(app: FastAPI, path: str) -> RouteInfo:
    for ruta in effective_routes(app)[0]:
        if ruta.path == path:
            return ruta
    raise AssertionError(path)


async def _otra_dependencia(p: Annotated[Principal, Depends(require_role("admin"))]) -> Principal:
    return p


def _app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/parametro")
    async def parametro(p: Annotated[Principal, Depends(require_role("admin"))]) -> dict[str, str]:
        return {}

    @app.get("/en-ruta", dependencies=[Depends(require_role("coach"))])
    async def en_ruta() -> dict[str, str]:
        return {}

    router = APIRouter(dependencies=[Depends(require_role("admin", "coach"))])

    @router.get("/en-router")
    async def en_router() -> dict[str, str]:
        return {}

    app.include_router(router)

    @app.get("/anidada")
    async def anidada(p: Annotated[Principal, Depends(_otra_dependencia)]) -> dict[str, str]:
        return {}

    @app.get("/sin-nada")
    async def sin_nada() -> dict[str, str]:
        return {}

    @app.get("/api/v1/auth/login")
    async def login_get() -> dict[str, str]:
        return {}

    @app.post("/api/v1/auth/login")
    async def login_post() -> dict[str, str]:
        return {}

    @app.get("/api/v1/tv/today")
    async def tv_sin_token() -> dict[str, str]:
        return {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {}

    return app


def test_detecta_la_dependencia_en_todas_las_formas() -> None:
    app = _app()
    for path in ("/parametro", "/en-ruta", "/en-router", "/anidada"):
        assert route_has_role_dependency(_ruta(app, path)) is True, path
    assert route_has_role_dependency(_ruta(app, "/sin-nada")) is False


def test_unprotected_routes_lista_lo_que_falta() -> None:
    app = _app()
    assert unprotected_routes(app) == [
        "GET /api/v1/auth/login",  # solo POST está en la lista blanca
        "GET /api/v1/tv/today",  # pública solo con la marca de token de dispositivo (N-44)
        "GET /sin-nada",
    ]


def test_tv_con_marca_de_token_de_dispositivo_cuenta_como_protegida() -> None:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    async def device_token() -> None:
        return None

    device_token.__apex_device_token__ = True  # type: ignore[attr-defined]

    @app.get("/api/v1/tv/today", dependencies=[Depends(device_token)])
    async def tv() -> dict[str, str]:
        return {}

    assert unprotected_routes(app) == []


def test_rutas_que_no_son_apiroute_se_reportan() -> None:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.routes.append(Route("/plano", endpoint=lambda r: PlainTextResponse("x")))
    app.routes.append(Mount("/estatico", app=FastAPI()))
    reportadas = unprotected_routes(app)
    assert any("/plano" in r for r in reportadas) and any("/estatico" in r for r in reportadas)
