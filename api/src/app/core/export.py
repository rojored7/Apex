"""Exportaciones CSV (S5-B12, US-138, US-139; S5-D41, S5-D60, S5-D82, S5-D247; M-10, L-6).

Sin dependencias de módulos de negocio (`app.modules`): solo la biblioteca estándar y `core`.

- `EXPORT_MAX_ROWS` (20.000): tope por defecto de filas de una exportación; el valor en uso sale de
  `Settings.EXPORT_MAX_ROWS` (más de ese tope: `ExportTooLarge`, 422 `export_too_large`, ANTES de
  enviar cabeceras).
- `escape_formula(value)`: antepone un apóstrofo a la celda de texto que empieza por `=`, `+`, `-`,
  `@`, tabulador o retorno de carro (inyección de fórmulas en hojas de cálculo). Solo cadenas: los
  enteros de monto no se escapan (L-6: el teléfono `+57...` también recibe el apóstrofo).
- `csv_header(header)` y `csv_rows(rows)`: las piezas del CSV (S5-D247). El encabezado lleva el BOM
  UTF-8 una sola vez; las filas van con `;`, `\r\n` y comillas mínimas, un fragmento por llamada
  (un lote). `csv_stream(header, rows)` las compone para el caso síncrono y perezoso. Ninguna
  escapa fórmulas: lo hace quien arma la fila.
- `single_flight(user_id)`: un flujo por usuario en memoria (un solo proceso del api, RUNBOOK §1);
  el segundo lanza `ExportInProgress` (409 `export_in_progress`). Sirve como gestor de contexto o
  con `acquire()`/`release()` (idempotente) cuando el cuerpo en streaming sobrevive al manejador;
  `guarded_body` lo suelta al terminar, abortar o cancelarse el cuerpo. Un candado que nadie soltó
  (cuerpo que no llegó a empezar) caduca a los `FLIGHT_STALE_S` segundos.
- Flujo único por PROCESO del api (S5-D258): `single_flight` vive en la memoria del proceso. Vale
  porque APEX corre un solo api con un solo worker de uvicorn (un servidor, D5, `compose.yml`);
  con réplicas el candado pasaría a un advisory lock de Postgres (dueño: quien añada réplicas).
- El cierre auditado y la paginación por llave viven en `core/export_db.py` (S5-D257): este
  archivo no importa SQLAlchemy, `audit` ni `db` (lo fija `test_core_import_direction`).
- `ExportStream`: lo que devuelve el service de cada módulo al router: filas contadas, nombre del
  archivo y el generador del cuerpo (que abre su PROPIA sesión, no la de la petición).
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Final
from uuid import UUID

from app.core.errors import ConflictError, ValidationFailed

EXPORT_MAX_ROWS: Final = 20_000
CSV_DELIMITER: Final = ";"
CSV_BOM: Final = "﻿"
CSV_NEWLINE: Final = "\r\n"
FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")
FLIGHT_STALE_S: Final = 900.0

# Usuario -> (dueño, instante monótono del último latido). Un solo proceso del api (RUNBOOK §1).
_EN_CURSO: dict[UUID, tuple[object, float]] = {}


class ExportInProgress(ConflictError):
    """409 `export_in_progress`: el usuario ya tiene una exportación en curso (S5-D82)."""

    code = "export_in_progress"
    default_message = "Ya tienes una exportación en curso. Espera a que termine."


class ExportTooLarge(ValidationFailed):
    """422 `export_too_large`: más filas que el tope (S5-D41); sale antes de las cabeceras."""

    code = "export_too_large"
    default_message = "La exportación supera el máximo de filas. Acota los filtros."


@dataclass(frozen=True)
class ExportStream:
    """Resultado de preparar una exportación (ya validada y auditada su apertura).

    `body()` devuelve el generador de bytes del CSV; al terminar, abortar o cortarse el cliente
    escribe la fila de cierre con una sesión propia (S5-D60)."""

    export_id: UUID
    rows: int
    filename: str
    body: Callable[[], AsyncIterator[bytes]]


def escape_formula(value: str) -> str:
    """Neutraliza una celda de texto que una hoja de cálculo leería como fórmula."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _escribir(rows: Iterable[Sequence[str | int]], delimiter: str, prefijo: str = "") -> bytes:
    destino = io.StringIO(newline="")
    escritor = csv.writer(
        destino, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator=CSV_NEWLINE
    )
    escritor.writerows(rows)
    return (prefijo + destino.getvalue()).encode("utf-8")


def csv_header(header: Sequence[str], *, delimiter: str = CSV_DELIMITER) -> bytes:
    """BOM UTF-8 y la fila de encabezado; va una sola vez al inicio del cuerpo."""
    return _escribir([header], delimiter, CSV_BOM)


def csv_rows(rows: Iterable[Sequence[str | int]], *, delimiter: str = CSV_DELIMITER) -> bytes:
    """Las filas de un lote, con comillas mínimas y `\r\n`; los enteros salen tal cual."""
    return _escribir(rows, delimiter)


def csv_stream(
    header: Sequence[str],
    rows: Iterable[Sequence[str | int]],
    *,
    delimiter: str = CSV_DELIMITER,
) -> Iterator[bytes]:
    """Cabecera primero y un fragmento por fila; perezoso (consume `rows` a medida que se pide)."""
    yield csv_header(header, delimiter=delimiter)
    for fila in rows:
        yield csv_rows([fila], delimiter=delimiter)


class Flight:
    """El flujo único de un usuario (S5-D82): gestor de contexto o `acquire`/`release`.

    Cada `Flight` es dueño de su entrada (S5-D254): `release` nunca retira el candado de un flujo
    posterior que reemplazó al caducado, y `touch` renueva el instante mientras el cuerpo avanza."""

    def __init__(self, user_id: UUID) -> None:
        self._user_id = user_id
        self._dueno = object()

    def _es_mio(self) -> bool:
        actual = _EN_CURSO.get(self._user_id)
        return actual is not None and actual[0] is self._dueno

    def acquire(self) -> None:
        """Toma el flujo o lanza `ExportInProgress`; un candado caducado se reemplaza."""
        ahora = time.monotonic()
        actual = _EN_CURSO.get(self._user_id)
        if actual is not None and ahora - actual[1] < FLIGHT_STALE_S:
            raise ExportInProgress()
        _EN_CURSO[self._user_id] = (self._dueno, ahora)

    def touch(self) -> None:
        """Latido: renueva el instante del candado propio (el cuerpo sigue avanzando)."""
        if self._es_mio():
            _EN_CURSO[self._user_id] = (self._dueno, time.monotonic())

    def release(self) -> None:
        """Suelta el flujo si sigue siendo de este objeto; llamarlo de nuevo no hace nada."""
        if self._es_mio():
            del _EN_CURSO[self._user_id]

    def __enter__(self) -> None:
        self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def single_flight(user_id: UUID) -> Flight:
    return Flight(user_id)


async def guarded_body(flight: Flight, body: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Entrega el cuerpo y suelta el flujo del usuario al terminar, fallar o cancelarse."""
    try:
        async for trozo in body:
            flight.touch()
            yield trozo
    finally:
        flight.release()
        cerrar = getattr(body, "aclose", None)
        if cerrar is not None:  # cierra el cuerpo interno: su `finally` escribe el cierre
            await cerrar()


async def begin_export(
    user_id: UUID, prepare: Callable[[], Awaitable[ExportStream]]
) -> tuple[ExportStream, AsyncIterator[bytes]]:
    """Toma el flujo único del usuario (409 si ya tiene uno), prepara la exportación y devuelve
    `(flujo, cuerpo)`. Si preparar falla (422, 503...) el flujo se suelta; si sale bien lo suelta
    el cuerpo al terminar. Todo antes de enviar cabeceras (S5-D41, S5-D82)."""
    vuelo = single_flight(user_id)
    vuelo.acquire()
    try:
        flujo = await prepare()
    except BaseException:
        vuelo.release()
        raise
    return flujo, guarded_body(vuelo, flujo.body())
