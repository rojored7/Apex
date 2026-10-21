"""Toda operación publica `ErrorResponse` en sus 4xx y 5xx; no existe `HTTPValidationError` (US-017, T4 y T8).

Hasta US-020 se construye una app de prueba con `responses=ERROR_RESPONSES` y
`register_error_handlers`; US-020 la reemplaza por `create_app()`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import ERROR_RESPONSES, register_error_handlers


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
