"""`WodResultSuperseded` (S9-B5, US-181; S9-D7): el evento de una corrección.

`record_result` lo emite SOLO cuando hay `supersedes_id`, tras el `INSERT` del resultado nuevo y
ANTES de `WodResultRecorded` y `WodResultValidated` (así el récord del anterior se invalida antes
de que el nuevo derive). Lleva solo ids. No se emite al registrar sin corrección, ni al anular, ni
cuando la corrección se rechaza antes del `INSERT`.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.core.errors import DomainError
from app.modules.results import service
from app.modules.results.events import (
    WodResultRecorded,
    WodResultSuperseded,
    WodResultValidated,
    WodResultVoided,
)
from app.modules.results.schemas import VoidIn
from tests.conftest import CapturarEventos
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

TRES = (WodResultSuperseded, WodResultRecorded, WodResultValidated)


async def test_la_correccion_emite_el_evento_con_los_cuatro_ids(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    e = await escena(session, con_clase=False)
    primero = await registrar(session, e, seconds=300)
    recibidos = capturar_eventos(WodResultSuperseded)

    nuevo = await registrar(session, e, seconds=290, supersedes_id=primero.id)

    assert len(recibidos) == 1
    evento = recibidos[0]
    assert evento.old_result_id == primero.id
    assert evento.new_result_id == nuevo.id
    assert evento.member_id == e.socio_id
    assert evento.wod_id == e.wod_id


async def test_el_orden_es_superseded_recorded_validated(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    e = await escena(session, con_clase=False)
    primero = await registrar(session, e, seconds=300)
    recibidos = capturar_eventos(*TRES)

    await registrar(session, e, seconds=290, supersedes_id=primero.id)

    assert [type(ev) for ev in recibidos] == [
        WodResultSuperseded,
        WodResultRecorded,
        WodResultValidated,
    ]


async def test_registrar_sin_correccion_no_emite_superseded(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    e = await escena(session, con_clase=False)
    recibidos = capturar_eventos(*TRES)

    await registrar(session, e, seconds=300)

    assert [type(ev) for ev in recibidos] == [WodResultRecorded, WodResultValidated]


async def test_al_emitirse_el_resultado_nuevo_ya_esta_insertado_y_el_anterior_apagado(
    session: AsyncSession,
) -> None:
    """Un suscriptor ve el `INSERT` hecho (el handler de `athletes` lee el resultado nuevo) y el
    anterior ya no vigente: el contrato del orden de S9-D7."""
    e = await escena(session, con_clase=False)
    primero = await registrar(session, e, seconds=300)
    vistos: list[tuple[int, bool | None]] = []

    async def espia(evento: WodResultSuperseded, sesion: AsyncSession) -> None:
        nuevo = await sesion.scalar(
            text("SELECT count(*) FROM results.wod_results WHERE id = :i"),
            {"i": evento.new_result_id},
        )
        anterior = await sesion.scalar(
            text("SELECT is_current FROM results.wod_results WHERE id = :i"),
            {"i": evento.old_result_id},
        )
        vistos.append((int(nuevo or 0), anterior))

    events.subscribe(WodResultSuperseded, espia)

    await registrar(session, e, seconds=290, supersedes_id=primero.id)

    assert vistos == [(1, False)]


async def test_anular_no_emite_superseded(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    e = await escena(session, con_clase=False)
    primero = await registrar(session, e, seconds=300)
    recibidos = capturar_eventos(WodResultSuperseded, WodResultVoided)

    with actor_scope(e.coach):
        await service.void_result(
            session, primero.id, VoidIn(reason="Error de digitación"), by=e.coach
        )

    assert [type(ev) for ev in recibidos] == [WodResultVoided]


async def test_una_correccion_rechazada_antes_del_insert_no_emite(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    """`supersedes_id` que no es el vigente: 409 y ningún evento (nada se insertó)."""
    e = await escena(session, con_clase=False)
    await registrar(session, e, seconds=300)
    recibidos = capturar_eventos(*TRES)
    ajeno = UUID(int=999)

    with pytest.raises(DomainError) as info:
        async with session.begin_nested():
            await registrar(session, e, seconds=290, supersedes_id=ajeno)

    assert info.value.status == 409
    assert recibidos == []


async def test_una_segunda_correccion_emite_su_propio_evento_con_el_vigente_como_anterior(
    session: AsyncSession, capturar_eventos: CapturarEventos
) -> None:
    e = await escena(session, con_clase=False)
    primero = await registrar(session, e, seconds=300)
    segundo = await registrar(session, e, seconds=290, supersedes_id=primero.id)
    recibidos = capturar_eventos(WodResultSuperseded)

    tercero = await registrar(session, e, seconds=280, supersedes_id=segundo.id)

    assert [(ev.old_result_id, ev.new_result_id) for ev in recibidos] == [(segundo.id, tercero.id)]


def test_el_evento_es_inmutable_solo_ids_y_sale_por_la_fachada() -> None:
    campos = {c.name: c.type for c in dataclasses.fields(WodResultSuperseded)}
    propios: dict[str, Any] = {k: v for k, v in campos.items() if k != "occurred_at"}

    assert set(propios) == {"old_result_id", "new_result_id", "member_id", "wod_id"}
    assert all(str(v) in {"UUID", "<class 'uuid.UUID'>"} for v in propios.values())
    assert service.WodResultSuperseded is WodResultSuperseded
    assert "WodResultSuperseded" in service.__all__
    with pytest.raises(dataclasses.FrozenInstanceError):
        evento = WodResultSuperseded(
            old_result_id=UUID(int=1),
            new_result_id=UUID(int=2),
            member_id=UUID(int=3),
            wod_id=UUID(int=4),
        )
        evento.wod_id = UUID(int=5)  # type: ignore[misc]
