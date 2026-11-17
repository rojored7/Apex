"""Dos altas manuales a la vez del mismo socio se serializan (S9-B1, US-180; S9-D9, S9-D10).

Con commit real y dos conexiones. La alta toma `lock_member` ANTES de decidir cuál es el vigente:
la segunda espera a la primera (visible en `pg_locks`), ve su récord ya confirmado y, con la misma
marca, queda como histórico. Sin el candado ambas verían «sin vigente», las dos serían vigentes y
se emitirían dos `PersonalRecordSet`.

Módulo aparte: `bus_confirmado` (llaves con commit) no convive con `bus_listo` (transacción).
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.athletes import service
from app.modules.athletes.events import PersonalRecordSet
from app.modules.athletes.schemas import RecordIn
from tests.athletes._apoyo import cuerpo_rm
from tests.conftest import CapturarEventos
from tests.factories.wods import make_movement
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")

ESPERA_MAX_S = 10.0


async def _alta(
    session: AsyncSession,
    member_id: UUID,
    movement_id: UUID,
    value_g: int,
    achieved_on: str = "2026-10-20",
) -> bool:
    """El alta de una petición SIN confirmar; devuelve `is_current`."""
    with actor_scope(SYSTEM_USER_ID):
        salida = await service.add_record(
            session,
            member_id,
            RecordIn.model_validate(
                cuerpo_rm(movement_id, value_g=value_g, achieved_on=achieved_on)
            ),
            by=SYSTEM_USER_ID,
        )
    return bool(salida.is_current)


async def _esperando_candado(engine: AsyncEngine, pid: int) -> None:
    limite = time.monotonic() + ESPERA_MAX_S
    consulta = text("SELECT count(*) FROM pg_locks WHERE pid = :p AND NOT granted")
    while time.monotonic() < limite:
        async with engine.connect() as conexion:
            if await conexion.scalar(consulta, {"p": pid}):
                return
        await asyncio.sleep(0.05)
    raise AssertionError("la segunda conexión nunca quedó esperando un candado")


async def test_dos_altas_iguales_a_la_vez_una_vigente_una_historica_y_un_solo_evento(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    capturar_eventos: CapturarEventos,
) -> None:
    una, otra = dos_sesiones
    miembro = await socio(una, consentido=True)
    mov = await make_movement(una, SYSTEM_USER_ID, "Serie", "kg")
    member_id, movement_id = miembro.id, mov.id
    una.expunge_all()
    recibidos = capturar_eventos(PersonalRecordSet)
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)

    primera = await _alta(una, member_id, movement_id, 100_000)  # candado tomado, sin confirmar
    contraria = asyncio.create_task(
        _alta(otra, member_id, movement_id, 100_000, "2026-10-21")  # L1: no es el idéntico
    )
    try:
        try:
            await _esperando_candado(engine, pid)
            assert not contraria.done(), "la segunda alta debe esperar a la primera"
        finally:
            await una.commit()  # nunca dejar el candado tomado
        segunda = await asyncio.wait_for(contraria, 30)
        await otra.commit()
    finally:
        if not contraria.done():
            contraria.cancel()
        await asyncio.gather(contraria, return_exceptions=True)
        await otra.rollback()

    assert primera is True
    assert segunda is False  # vio el récord de la primera y, a igual marca, gana el más antiguo
    assert len(recibidos) == 1
    cuenta = await una.scalar(
        text("SELECT count(*) FROM athletes.personal_records WHERE member_id = :m"),
        {"m": member_id},
    )
    assert cuenta == 2


async def test_dos_altas_de_distinto_valor_a_la_vez_dejan_un_solo_vigente_el_mayor(
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    capturar_eventos: CapturarEventos,
) -> None:
    una, otra = dos_sesiones
    miembro = await socio(una, consentido=True)
    mov = await make_movement(una, SYSTEM_USER_ID, "Serie dos", "kg")
    member_id, movement_id = miembro.id, mov.id
    una.expunge_all()
    recibidos = capturar_eventos(PersonalRecordSet)
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)

    primera = await _alta(una, member_id, movement_id, 100_000)
    contraria = asyncio.create_task(_alta(otra, member_id, movement_id, 90_000))
    try:
        try:
            await _esperando_candado(engine, pid)
        finally:
            await una.commit()
        segunda = await asyncio.wait_for(contraria, 30)
        await otra.commit()
    finally:
        if not contraria.done():
            contraria.cancel()
        await asyncio.gather(contraria, return_exceptions=True)
        await otra.rollback()

    assert (primera, segunda) == (True, False)
    assert len(recibidos) == 1
