"""Logs JSON a stdout sin datos sensibles (US-018).

- `redact`: por clave (`SENSITIVE_KEYS`, sin distinguir mayúsculas) y por forma del
  valor (blobs `apx1.` y JWT), recursiva, también dentro del texto del mensaje y
  de la traza.
- S2-B3 (blueprint 7.2): el token de un enlace `/restablecer/<token>` y el valor de la
  cookie `apex_refresh=<valor>` (los atributos de la cookie se conservan); las claves
  `activation_url`, `url` y `set-cookie` se redactan enteras.
- `JsonFormatter`: una línea JSON por registro con `timestamp` UTC, `level`,
  `logger`, `message`, `request_id` y los extras.
- `configure_logging`: idempotente; apaga el log de acceso de Uvicorn (lo reemplaza
  el middleware) y deja `sqlalchemy.engine` en WARNING.
- `RequestLogMiddleware`: ASGI puro (no `BaseHTTPMiddleware`, para que el
  `ContextVar` llegue al endpoint); asigna `request_id`, lo devuelve en
  `X-Request-ID` y escribe una línea `http_request` sin cuerpo, query ni cabeceras.

Este módulo se llama `logging` dentro de `app.core`; los imports son absolutos,
así que `import logging` sigue siendo la biblioteca estándar.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.context import current_actor, request_id_var
from app.core.crypto.oplog import begin_unit_of_work

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "refresh_token",
        "access_token",
        "authorization",
        "cookie",
        "document",
        "phone",
        "email",
        "birth_date",
        "emergency_contact",
        "kek",
        "dek",
        "secret",
        "database_url",
        "activation_url",
        "url",
        "set-cookie",
    }
)
REDACTED = "[redacted]"
_BLOB = re.compile(r"apx1\.[A-Za-z0-9._-]+")
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_DSN = re.compile(r"://[^@/\s]+@")  # credenciales dentro de una URL: usuario:clave@
# Enlace de un solo uso: el segmento que sigue a `/restablecer/` es el token (blueprint 7.2).
_RESET_LINK = re.compile(r"(/restablecer/|%2Frestablecer%2F)[^\s/?#\"'&<>%]+", re.IGNORECASE)
# Valor de la cookie del refresh, hasta el primer separador de atributos.
_REFRESH_COOKIE = re.compile(r"(apex_refresh=)[^;\s,\"']+")
_ATRIBUTOS_ESTANDAR = set(vars(logging.LogRecord("x", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
}
_MARCA = "_apex_json_handler"

access_logger = logging.getLogger("app.access")


def redact_text(text: str) -> str:
    """Reemplaza blobs `apx1.`, JWT, credenciales de URL, tokens de `/restablecer/` y el valor
    de `apex_refresh=` dentro de un texto libre."""
    limpio = _DSN.sub("://[redacted]@", _JWT.sub(REDACTED, _BLOB.sub(REDACTED, text)))
    limpio = _RESET_LINK.sub(rf"\g<1>{REDACTED}", limpio)
    return _REFRESH_COOKIE.sub(rf"\g<1>{REDACTED}", limpio)


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact(value)
    if isinstance(value, list | tuple):
        return [_redact_value(v) for v in value]
    if isinstance(value, str):
        if value.startswith("apx1.") or _JWT.fullmatch(value):
            return REDACTED
        return redact_text(value)
    return value


def redact(record: Mapping[str, Any]) -> dict[str, Any]:
    """Función pura: copia redactada del registro, recursiva sobre dict y list."""
    return {
        str(clave): (REDACTED if str(clave).lower() in SENSITIVE_KEYS else _redact_value(valor))
        for clave, valor in record.items()
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for clave, valor in record.__dict__.items():
            if clave not in _ATRIBUTOS_ESTANDAR and not clave.startswith("_"):
                datos[clave] = valor
        if record.exc_info:
            datos["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            datos["exception"] = record.exc_text
        if record.stack_info:
            datos["stack"] = self.formatStack(record.stack_info)
        return json.dumps(redact(datos), ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """Un handler JSON a stdout con el nivel de `LOG_LEVEL`. Idempotente."""
    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        if getattr(handler, _MARCA, False):
            raiz.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    setattr(handler, _MARCA, True)
    raiz.addHandler(handler)
    raiz.setLevel(settings.LOG_LEVEL)

    access_logger.disabled = False
    acceso = logging.getLogger("uvicorn.access")
    acceso.handlers.clear()
    acceso.propagate = False
    acceso.disabled = True
    for nombre in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(nombre)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # httpx y httpcore registran la URL completa (query, tokens) en INFO: solo avisos.
    for nombre in ("httpx", "httpcore"):
        logging.getLogger(nombre).setLevel(logging.WARNING)


class RequestLogMiddleware:
    """Una línea `http_request` por petición y `X-Request-ID` en la respuesta."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Nunca se reutiliza un X-Request-ID del cliente: evita inyectar texto en los logs.
        request_id = uuid4().hex
        token = request_id_var.set(request_id)
        # US-034: current_user fija el actor y no lo resetea (el commit de get_session corre
        # en su teardown y lo necesita); se limpia aquí, cuando la petición ya terminó.
        token_actor = current_actor.set(None)
        begin_unit_of_work()  # US-029: buffer de crypto_ops creado aquí, visible desde hilos
        inicio = time.perf_counter()
        estado = {"status": 500}

        async def send_con_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                estado["status"] = int(message["status"])
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_con_id)
        finally:
            current_actor.reset(token_actor)
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
            ruta = scope.get("route")
            path = getattr(ruta, "path_format", None) or getattr(ruta, "path", None)
            access_logger.info(
                "http_request",
                extra={
                    "method": scope.get("method"),
                    "path": path or scope.get("path", ""),
                    "status": estado["status"],
                    "duration_ms": duracion_ms,
                },
            )
            request_id_var.reset(token)
