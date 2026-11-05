"""Ayudas de las pruebas de exportación CSV (S5-B12, US-138, US-139). Rojo B12.

- `parsear(cuerpo)`: comprueba el BOM UTF-8 y los `\\r\\n` y devuelve `(cabecera, filas)` leídas con
  `;` y comillas.
- `sesion_propia(session)`: hace que `db.get_sessionmaker()` entregue la sesión de la prueba (y
  cuenta en `.aperturas` cuántas veces se pidió). El
  generador del CSV abre su PROPIA sesión (la de la petición ya cerró); en las pruebas todo vive
  en una transacción con savepoint, así que la "sesión propia" es esa misma, sin cerrarla.
- `filas_export(session, tabla)`: filas `export` de `audit.audit_log` de la tabla, por `seq`.
- `ops_export(session)`: `(data_class, count)` ordenado de las filas `decrypt` con propósito
  `export` de `crypto.crypto_ops`.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db

BOM = b"\xef\xbb\xbf"


def parsear(cuerpo: bytes) -> tuple[list[str], list[list[str]]]:
    assert cuerpo.startswith(BOM), cuerpo[:8]
    contenido = cuerpo[len(BOM) :].decode("utf-8")
    assert contenido.endswith("\r\n"), repr(contenido[-4:])
    filas = list(csv.reader(io.StringIO(contenido, newline=""), delimiter=";"))
    return filas[0], filas[1:]


class _Contexto:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> None:
        return None


class _Fabrica:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.aperturas = 0

    def __call__(self) -> _Contexto:
        self.aperturas += 1
        return _Contexto(self._session)


@contextmanager
def sesion_propia(session: AsyncSession) -> Iterator[_Fabrica]:
    fabrica = _Fabrica(session)
    db.configure_sessionmaker(fabrica)  # type: ignore[arg-type]
    try:
        yield fabrica
    finally:
        db.configure_sessionmaker(None)


async def filas_export(session: AsyncSession, tabla: str) -> list[dict[str, Any]]:
    consulta = text(
        "SELECT seq, user_id, record_id, after FROM audit.audit_log "
        "WHERE action = 'export' AND table_name = :t ORDER BY seq"
    )
    return [dict(f._mapping) for f in await session.execute(consulta, {"t": tabla})]


async def ops_export(session: AsyncSession) -> list[tuple[str, int]]:
    consulta = text(
        "SELECT data_class, count FROM crypto.crypto_ops "
        "WHERE verb = 'decrypt' AND purpose = 'export' ORDER BY data_class, count"
    )
    return [
        (f._mapping["data_class"], f._mapping["count"]) for f in await session.execute(consulta)
    ]


async def pedir_y_cortar(
    app: Any, ruta: str, params: dict[str, str], cabeceras: dict[str, str], *, cortar_tras: int = 2
) -> int:
    """GET ASGI crudo cuyo cliente se desconecta (`send` lanza `OSError`) tras `cortar_tras`
    fragmentos del cuerpo (S5-D252). Devuelve cuántos fragmentos alcanzó a recibir."""
    import asyncio
    from urllib.parse import urlencode

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": ruta,
        "raw_path": ruta.encode(),
        "root_path": "",
        "query_string": urlencode(params).encode(),
        "headers": [
            (b"host", b"t"),
            *((k.lower().encode(), v.encode()) for k, v in cabeceras.items()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("t", 80),
    }
    pedido = [{"type": "http.request", "body": b"", "more_body": False}]
    fragmentos = 0

    async def receive() -> dict[str, Any]:
        if pedido:
            return pedido.pop()
        await asyncio.Event().wait()  # el cliente no dice nada más
        raise AssertionError

    async def send(mensaje: dict[str, Any]) -> None:
        nonlocal fragmentos
        if mensaje["type"] == "http.response.body" and mensaje.get("body"):
            fragmentos += 1
            if fragmentos >= cortar_tras:
                raise OSError("cliente desconectado")

    try:
        await app(scope, receive, send)
    except Exception:  # noqa: S110 - el corte del cliente llega como excepción o se traga
        pass
    return fragmentos
