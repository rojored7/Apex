"""Envelope único de errores (US-017).

Toda respuesta de error del api es `{ "error": { "code", "message", "field"?,
"existing_id"? } }` con `application/json`, también los 404 y 405 de Starlette, el
422 de validación y el 500. El 500 nunca lleva `str(exc)`, traza ni SQL; el 422
nunca repite el valor recibido.

Cada módulo define sus errores en `exceptions.py` heredando de `DomainError`.
Este archivo solo importa FastAPI, Starlette, Pydantic, `logging` y
`core/context.py` a nivel de módulo; el gancho de OpenAPI importa `core/security.py` de forma
perezosa (el ciclo `security -> db -> errors` impide hacerlo arriba).

OpenAPI (M7 de la revisión general del Sprint 2): cada router o ruta declara solo los errores
que puede devolver con `responses_for(401, 403, ...)`; el gancho del esquema agrega `500` a toda
operación y convierte en `ErrorResponse` los códigos del catálogo (también el `422` que FastAPI
pone a las rutas con parámetros o cuerpo). Antes la app declaraba los ocho códigos en las 31
operaciones, incluido `/health`. S3-W0-2 (S3-D67 corregida por E16): toda operación con seguridad
declarada (una dependencia con la marca `__apex_roles__`) recibe además `503` `ErrorResponse`
(`busy`); el `503` no entra en el catálogo, así `/health` conserva su `503` `HealthOut` y las
públicas no lo declaran.
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
MENSAJE_503 = "Base de datos ocupada"
"""Descripción OpenAPI del `503` `busy` de las operaciones con rol (fuera de `_DESCRIPCIONES`)."""


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
        self.headers: dict[str, str] = {}
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


class TooManyRequestsError(DomainError):
    status = 429
    code = "rate_limited"
    default_message = "Demasiados intentos. Espera un momento."

    def __init__(self, retry_after_s: int) -> None:
        super().__init__()
        self.headers = {"Retry-After": str(max(1, retry_after_s))}


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
    429: "Demasiados intentos",
}

# Catálogo completo (pruebas y apps de prueba). El api real declara por ruta con `responses_for`.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    codigo: {"model": ErrorResponse, "description": descripcion}
    for codigo, descripcion in _DESCRIPCIONES.items()
}


def responses_for(*codes: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` de una ruta o router con solo esos códigos del catálogo (M7). Un código fuera
    del catálogo es un error de programación: `ValueError` al importar el router."""
    desconocidos = [c for c in codes if c not in _DESCRIPCIONES]
    if desconocidos:
        raise ValueError(f"código de error fuera del catálogo: {desconocidos}")
    return {c: dict(ERROR_RESPONSES[c]) for c in codes}


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
    respuesta = _responder(exc.status, exc.body())
    if exc.status == 401:
        respuesta.headers["WWW-Authenticate"] = "Bearer"  # US-034: toda 401 lleva el esquema
    for nombre, valor in exc.headers.items():  # US-036: Retry-After en el 429
        respuesta.headers[nombre] = valor
    return respuesta


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


def _operaciones_con_rol(app: FastAPI) -> set[tuple[str, str]]:
    """`(método en minúsculas, ruta)` de cada operación con `require_role` en su árbol de
    dependencias (marca `__apex_roles__`). Import perezoso: `security` importa `db`, que importa
    este módulo."""
    from app.core.security import effective_routes, route_has_role_dependency

    return {
        (metodo.lower(), ruta.path)
        for ruta in effective_routes(app)[0]
        if route_has_role_dependency(ruta)
        for metodo in ruta.methods
    }


def _publicar_error_response(app: FastAPI) -> None:
    """Reemplaza `HTTPValidationError` por `ErrorResponse` en los códigos del catálogo que la
    ruta declara (o el `422` automático de FastAPI) y agrega `500` a toda operación y `503`
    (`busy`) a las que tienen rol. Un código fuera del catálogo (el `503` de `/health`, con
    `HealthOut`) queda como lo declaró la ruta."""

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
        con_rol = _operaciones_con_rol(app)
        for ruta, operaciones in esquema.get("paths", {}).items():
            for metodo, operacion in operaciones.items():
                if not isinstance(operacion, dict) or "responses" not in operacion:
                    continue
                respuestas = operacion["responses"]
                for codigo in list(respuestas):
                    if codigo.isdigit() and int(codigo) in _DESCRIPCIONES:
                        descripcion = (
                            respuestas[codigo].get("description") or _DESCRIPCIONES[int(codigo)]
                        )
                        respuestas[codigo] = {"description": descripcion, **contenido}
                respuestas.setdefault("500", {"description": _DESCRIPCIONES[500], **contenido})
                if (metodo, ruta) in con_rol:
                    respuestas.setdefault("503", {"description": MENSAJE_503, **contenido})
        app.openapi_schema = esquema
        return esquema

    app.openapi = openapi  # type: ignore[method-assign]
