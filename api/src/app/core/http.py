"""Dependencias HTTP compartidas por los routers (revisión Python M6).

- `no_store`: `Cache-Control: no-store` en la respuesta. Va en toda ruta con rol (las
  respuestas con sesión llevan datos de personas o de configuración) y en las de sesión de
  `auth`; la prueba `tests/architecture/test_no_store_routes.py` lo exige. Nginx también lo pone
  en `/api/`, pero el api no depende del borde. Antes vivía en `auth/cookies.py` (privado de
  `auth`), por eso socios y planes no lo llevaban.

Solo importa FastAPI; ningún módulo de negocio.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, Final

from fastapi import Response
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

NO_STORE: Final = "no-store"


async def no_store(response: Response) -> None:
    """Dependencia: `dependencies=[Depends(no_store)]` en la ruta o en el `APIRouter`."""
    response.headers["Cache-Control"] = NO_STORE


class _CsvResponse(StreamingResponse):
    """`StreamingResponse` que cierra el cuerpo al terminar el envío, también si el cliente
    se desconecta o el cuerpo nunca empezó (S5-D252): el `finally` del generador escribe la fila
    de cierre y suelta el flujo del usuario sin depender del recolector."""

    def __init__(self, body: AsyncIterator[bytes], **kwargs: Any) -> None:
        super().__init__(body, **kwargs)
        self._cuerpo = body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            cerrar = getattr(self._cuerpo, "aclose", None)
            if cerrar is not None:
                await cerrar()


def csv_download(body: AsyncIterator[bytes], filename: str) -> StreamingResponse:
    """Descarga CSV en streaming (S5-B12, S5-D41): UTF-8, adjunto, `no-store` y `nosniff`."""
    return _CsvResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": NO_STORE,
        },
    )


# Solo ASCII imprimible sin separadores de ruta, comillas, `;` ni `%`: el nombre va sin comillas en
# `Content-Disposition`, así que un `;` añadiría parámetros y un carácter fuera de latin-1 haría
# fallar la codificación de la cabecera (revisión de seguridad de S6-B3).
_FUERA_DEL_NOMBRE: Final = re.compile(r'[^\x20-\x7e]|[/\\";%]')
CSP_DESCARGA: Final = "default-src 'none'; sandbox"


def _safe_filename(nombre: str) -> str:
    """Deja solo ASCII imprimible sin `/`, `\\`, comillas, `;`, `%`, controles ni `..`; vacío cae a
    `descarga.json`."""
    limpio = _FUERA_DEL_NOMBRE.sub("", nombre)
    while ".." in limpio:
        limpio = limpio.replace("..", "")
    return limpio.strip() or "descarga.json"


def file_download(body: bytes, *, filename: str, media_type: str) -> Response:
    """Descarga de un archivo ya armado en memoria (S6-B3): `attachment`, `no-store`, `nosniff`
    y una CSP que no deja ejecutar nada."""
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={_safe_filename(filename)}",
            "Cache-Control": NO_STORE,
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": CSP_DESCARGA,
        },
    )
