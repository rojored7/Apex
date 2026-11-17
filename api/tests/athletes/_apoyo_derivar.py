"""Apoyo de las pruebas de derivación de RM (S9-B3, US-181; S9-D10, S9-D30, S9-D42).

- `AlertasCapturadas` y la fixture `alertas` (se importa en `conftest.py`): un sink propio que
  anota `(code, context)`; la fixture lo registra y lo quita al salir.
- `escena_carga(session)`: un WOD `load` del 21 de octubre con dos movimientos; el principal
  (`movimientos[0]`) mide en kg. Sin clase (el resultado va por escritorio).
- `wod_extra(session, e, fecha)`: otro WOD `load` con los MISMOS movimientos (mismo principal).
- `poner(http, headers, e, **cambios)`: `PUT /results` real con una carga en gramos.
- `records_de(session, member_id)`: filas crudas de `athletes.personal_records` del socio.
- `vigente_g(filas)`: el mayor `value_g` de los RM NO invalidados (la regla N-45 sin desempate).
- `sentencias_de(session, contiene)`: cuenta las sentencias que mencionan alguna de las tablas.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alerts import register_sink, unregister_sink
from tests.athletes._apoyo import filas_de_records
from tests.factories.wods import make_wod
from tests.results._apoyo import Escena, escena

RESULTADOS = "/api/v1/results"
FECHA_HOY = "2026-10-21"


class AlertasCapturadas:
    """Sink de alertas que solo anota lo recibido (`code`, contexto)."""

    def __init__(self) -> None:
        self.recibidas: list[tuple[str, dict[str, object]]] = []

    def send(self, code: str, context: Any) -> None:
        self.recibidas.append((code, dict(context)))

    def de(self, code: str) -> list[dict[str, object]]:
        return [c for k, c in self.recibidas if k == code]


@pytest.fixture
def alertas() -> Iterator[AlertasCapturadas]:
    sink = AlertasCapturadas()
    register_sink(sink)
    try:
        yield sink
    finally:
        unregister_sink(sink)


async def escena_carga(session: AsyncSession) -> Escena:
    """WOD `load` de hoy (principal en kg), sin clase ni asistencia."""
    return await escena(session, score_type="load", time_cap_s=None, con_clase=False)


async def wod_extra(session: AsyncSession, e: Escena, fecha: str, titulo: str) -> UUID:
    """Otro WOD `load` con los mismos movimientos (y por lo tanto el mismo principal)."""
    wod = await make_wod(
        session,
        e.coach,
        list(e.movimientos),
        date=fecha,
        title=titulo,
        score_type="load",
        time_cap_s=None,
    )
    return wod.id


def cuerpo_put(e: Escena, **cambios: Any) -> dict[str, Any]:
    valores: dict[str, Any] = {
        "wod_id": str(e.wod_id),
        "member_id": str(e.socio_id),
        "level": "rx",
        "load_g": 100_000,
    }
    valores.update(cambios)
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in valores.items() if v is not None}


async def poner(http: AsyncClient, headers: dict[str, str], e: Escena, **cambios: Any) -> Response:
    return await http.put(RESULTADOS, json=cuerpo_put(e, **cambios), headers=headers)


async def records_de(session: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    return await filas_de_records(session, member_id)


def vigente_g(filas: list[dict[str, Any]]) -> int | None:
    """El mayor `value_g` entre los RM no invalidados (sin desempate: solo el valor)."""
    valores = [f["value_g"] for f in filas if f["kind"] == "rm" and f["invalidated_at"] is None]
    return max(valores) if valores else None


@contextmanager
def contar_sentencias(session: AsyncSession, tablas: Collection[str]) -> Iterator[list[str]]:
    """Las sentencias (sin SAVEPOINT ni RELEASE) que mencionan alguna de las `tablas`."""
    vistas: list[str] = []
    destino = session.sync_session.get_bind()

    def anotar(_c: Any, _cur: Any, sql: str, *_a: Any) -> None:
        if sql.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")):
            return
        if any(t in sql for t in tablas):
            vistas.append(sql)

    event.listen(destino, "before_cursor_execute", anotar)
    try:
        yield vistas
    finally:
        event.remove(destino, "before_cursor_execute", anotar)


Accion = Callable[[], Awaitable[Any]]
