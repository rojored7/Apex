"""Envelope único de errores (US-017).

Toda respuesta de error del api es `{ "error": { "code", "message", "field"?,
"existing_id"? } }` con `application/json`, también los 404 y 405 de Starlette, el
422 de validación y el 500. El 500 nunca lleva `str(exc)`, traza ni SQL; el 422
nunca repite el valor recibido.

Cada módulo define sus errores en `exceptions.py` heredando de `DomainError`.
Este archivo solo importa FastAPI, Starlette, Pydantic, `logging` y
`core/context.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_var

logger = logging.getLogger("app.errors")

PREFIJOS_LOC = frozenset({"body", "query", "path", "header", "cookie"})
MENSAJE_500 = "Ocurrió un error inesperado. Intente de nuevo."


class ErrorBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "member_duplicate",
                "message": "Ya existe un socio con este documento",
                "field": "document",
                "existing_id": "11111111-2222-3333-4444-555555555555",
            }
        }
    )

    code: str
    message: str
    field: str | None = None
    existing_id: UUID | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class DomainError(Exception):
    """Error de dominio con código estable. Las subclases fijan `status` y `code`."""

    status: int = 400
    code: str = "domain_error"
    default_message: str = "La operación no es válida."

    def __init__(
        self,
        code: str | None = None,
        message: str = "",
        *,
        field: str | None = None,
        existing_id: UUID | None = None,
        status: int | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.message = message or type(self).default_message
        self.field = field
        self.existing_id = existing_id
        self.status = status or type(self).status
        super().__init__(self.message)

    def body(self) -> ErrorBody:
        return ErrorBody(
            code=self.code, message=self.message, field=self.field, existing_id=self.existing_id
        )


class UnauthorizedError(DomainError):
    status = 401
    code = "unauthorized"
    default_message = "Inicia sesión para continuar."


class ForbiddenError(DomainError):
    status = 403
    code = "forbidden"
    default_message = "No tienes permiso para esta acción."


class NotFoundError(DomainError):
    status = 404
    code = "not_found"
    default_message = "No se encontró el recurso."


class ConflictError(DomainError):
    status = 409
    code = "conflict"
    default_message = "La operación entra en conflicto con el estado actual."


class ValidationFailed(DomainError):
    status = 422
    code = "validation_error"
    default_message = "Los datos enviados no son válidos."


_DESCRIPCIONES = {
    400: "Operación inválida",
    401: "Sin sesión válida",
    403: "Sin permiso",
    404: "No encontrado",
    409: "Conflicto con el estado actual",
    422: "Petición inválida",
    500: "Error inesperado",
}

# Para `FastAPI(responses=ERROR_RESPONSES)` o `include_router(..., responses=ERROR_RESPONSES)`.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    codigo: {"model": ErrorResponse, "description": descripcion}
    for codigo, descripcion in _DESCRIPCIONES.items()
}

_CODIGOS_HTTP: dict[int, tuple[str, str]] = {
    401: ("unauthorized", "Inicia sesión para continuar."),
    403: ("forbidden", "No tienes permiso para esta acción."),
    404: ("not_found", "No se encontró el recurso."),
    405: ("method_not_allowed", "Método no permitido para esta ruta."),
}


def validation_field(errors: Sequence[Mapping[str, Any]]) -> str | None:
    """Función pura: `("body", "items", 0, "amount_cop")` da `items[0].amount_cop`."""
    if not errors:
        return None
    partes = list(errors[0].get("loc", ()))
    if partes and partes[0] in PREFIJOS_LOC:
        partes = partes[1:]
    if not partes:
        return None
    salida = ""
    for parte in partes:
        if isinstance(parte, int):
            salida += f"[{parte}]"
        else:
            salida = f"{salida}.{parte}" if salida else str(parte)
    return salida


def _responder(status: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(error=body).model_dump(mode="json", exclude_none=True),
    )


async def _handler_dominio(request: Request, exc: DomainError) -> JSONResponse:
    return _responder(exc.status, exc.body())


async def _handler_validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
    campo = validation_field(exc.errors())
    mensaje = f"El campo {campo} no es válido." if campo else "La petición no es válida."
    return _responder(422, ErrorBody(code="validation_error", message=mensaje, field=campo))


async def _handler_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codigo, mensaje = _CODIGOS_HTTP.get(
        exc.status_code, ("http_error", "La petición no se pudo procesar.")
    )
    return _responder(exc.status_code, ErrorBody(code=codigo, message=mensaje))


async def _handler_inesperado(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "error inesperado",
        extra={"path": request.url.path, "request_id": request_id_var.get()},
    )
    return _responder(500, ErrorBody(code="internal_error", message=MENSAJE_500))


def register_error_handlers(app: FastAPI) -> None:
    """Registra los cuatro handlers y publica `ErrorResponse` en el OpenAPI."""
    app.add_exception_handler(DomainError, _handler_dominio)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handler_validacion)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handler_http)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handler_inesperado)
    _publicar_error_response(app)


def _publicar_error_response(app: FastAPI) -> None:
    """Reemplaza `HTTPValidationError` por `ErrorResponse` y lo declara en todo 4xx y 5xx."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        esquema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            servers=app.servers,
        )
        componentes = esquema.setdefault("components", {}).setdefault("schemas", {})
        componentes.pop("HTTPValidationError", None)
        componentes.pop("ValidationError", None)
        definicion = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
        componentes.update(definicion.pop("$defs", {}))
        componentes["ErrorResponse"] = definicion
        contenido = {
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
            }
        }
        for operaciones in esquema.get("paths", {}).values():
            for operacion in operaciones.values():
                if not isinstance(operacion, dict) or "responses" not in operacion:
                    continue
                respuestas = operacion["responses"]
                for codigo in list(respuestas):
                    if codigo[0] in "45":
                        descripcion = respuestas[codigo].get("description") or _DESCRIPCIONES.get(
                            int(codigo), "Error"
                        )
                        respuestas[codigo] = {"description": descripcion, **contenido}
                respuestas.setdefault("422", {"description": _DESCRIPCIONES[422], **contenido})
                respuestas.setdefault("500", {"description": _DESCRIPCIONES[500], **contenido})
        app.openapi_schema = esquema
        return esquema

    app.openapi = openapi  # type: ignore[method-assign]
