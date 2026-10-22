"""Toda operación publica `ErrorResponse` en sus 4xx y 5xx y no existe `HTTPValidationError`.

US-017, T4 y T8.

Hasta US-020 se construye una app de prueba con `responses=ERROR_RESPONSES` y
`register_error_handlers`; US-020 la reemplaza por `create_app()`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ERROR_RESPONSES, register_error_handlers
from app.main import create_app


class Entrada(BaseModel):
    nombre: str


def _app() -> FastAPI:
    app = FastAPI(responses=ERROR_RESPONSES)
    register_error_handlers(app)

    @app.get("/api/v1/cosas")
    async def listar() -> list[str]:
        return []

    @app.post("/api/v1/cosas", status_code=201)
    async def crear(entrada: Entrada) -> dict[str, str]:
        return {"nombre": entrada.nombre}

    return app


def _ref(respuesta: dict[str, Any]) -> str | None:
    contenido = respuesta.get("content", {}).get("application/json", {}).get("schema", {})
    return contenido.get("$ref")


def test_error_response_en_todas_las_operaciones() -> None:
    esquema = _app().openapi()
    assert "ErrorResponse" in esquema["components"]["schemas"]
    assert "HTTPValidationError" not in esquema["components"]["schemas"]
    assert "ValidationError" not in esquema["components"]["schemas"]
    for ruta, operaciones in esquema["paths"].items():
        for metodo, operacion in operaciones.items():
            respuestas = operacion["responses"]
            errores = {c: r for c, r in respuestas.items() if c[0] in "45"}
            assert errores, f"{metodo.upper()} {ruta} no declara respuestas de error"
            assert "500" in errores and "422" in errores, f"{metodo.upper()} {ruta}"
            for codigo, respuesta in errores.items():
                assert _ref(respuesta) == "#/components/schemas/ErrorResponse", (
                    f"{metodo.upper()} {ruta} {codigo}"
                )


def test_error_responses_cubre_los_codigos_del_contrato() -> None:
    assert {400, 401, 403, 404, 409, 422, 500} <= {int(c) for c in ERROR_RESPONSES}


# S3-W0-2 · 503 `busy` en el contrato real (S3-D67 corregida por E16; E7) ---------------------


def _ops_con_rol(app: FastAPI) -> set[tuple[str, str]]:
    from app.core.security import effective_routes, route_has_role_dependency

    return {
        (metodo.lower(), ruta.path)
        for ruta in effective_routes(app)[0]
        if route_has_role_dependency(ruta)
        for metodo in ruta.methods - {"HEAD", "OPTIONS"}
    }


def test_toda_operacion_con_rol_declara_500_y_503_como_error_response(
    settings_prueba: Settings,
) -> None:
    """E16: una operación con `require_role` abre sesión y puede responder 503 `busy`."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    esquema = app.openapi()
    con_rol = _ops_con_rol(app)
    assert con_rol, "la app real tiene rutas con rol"
    faltan: list[str] = []
    for ruta, operaciones in esquema["paths"].items():
        for metodo, operacion in operaciones.items():
            if (metodo, ruta) not in con_rol:
                continue
            for codigo in ("500", "503"):
                respuesta = operacion["responses"].get(codigo)
                if respuesta is None or _ref(respuesta) != "#/components/schemas/ErrorResponse":
                    faltan.append(f"{metodo.upper()} {ruta} {codigo}")
    assert faltan == [], "\n".join(faltan)


def test_las_operaciones_sin_rol_no_declaran_503_como_error_response(
    settings_prueba: Settings,
) -> None:
    """E16: `/health` y `/api/v1/health` conservan su 503 como `HealthOut`; las públicas (login,
    refresh, logout, forgot, reset) no declaran 503."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    esquema = app.openapi()
    con_rol = _ops_con_rol(app)
    publicas = [
        (metodo, ruta, operacion)
        for ruta, operaciones in esquema["paths"].items()
        for metodo, operacion in operaciones.items()
        if (metodo, ruta) not in con_rol
    ]
    assert {("get", "/health"), ("get", "/api/v1/health")} <= {(m, r) for m, r, _ in publicas}
    for metodo, ruta, operacion in publicas:
        respuesta = operacion["responses"].get("503")
        if ruta in {"/health", "/api/v1/health"}:
            assert respuesta is not None and _ref(respuesta) == "#/components/schemas/HealthOut"
        else:
            assert respuesta is None, f"{metodo.upper()} {ruta} no debe declarar 503"
