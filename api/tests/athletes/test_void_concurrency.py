"""L-3 (S9-A3; S9-D13, S9-D50): anular una medición con dos conexiones y commit real.

Cada prueba aísla UNA protección de `void_metric` (quitarla la pone en rojo):

- candado del socio (`lock_member`): dos anulaciones a la vez, la segunda espera y recibe 409;
- candado de la fila (`FOR UPDATE`): una conexión que retiene la fila SIN el candado del socio (la
  rotación de la llave) hace que la anulación espere EN la lectura de la fila y caiga en
  `lock_timeout` (503 `busy`), sin anular nada;
- relectura fresca (`populate_existing`): una copia vieja de la sesión no engaña: 409.

Módulo aparte: `bus_confirmado` (llaves con commit) no convive con `bus_listo` (transacción).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.db import translate_busy
from app.core.errors import DomainError
from app.modules.athletes import service
from app.modules.athletes.exceptions import MetricAlreadyVoided
from app.modules.athletes.models import BodyMetric
from tests.athletes._apoyo import alta
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_confirmado")

ESPERA_MAX_S = 10.0


async def _anular(session: AsyncSession, member_id: UUID, metric_id: UUID) -> Any:
    with actor_scope(SYSTEM_USER_ID):
        return await service.void_metric(
            session, member_id, metric_id, by=SYSTEM_USER_ID, role="admin"
        )


async def _esperando_candado(engine: AsyncEngine, pid: int) -> None:
    """Espera (con tope) a ver en `pg_locks` una fila `granted = false` del backend `pid`: la
    prueba afirma que la segunda conexión de verdad quedó esperando, no que pasó 0,5 s."""
    limite = time.monotonic() + ESPERA_MAX_S
    consulta = text("SELECT count(*) FROM pg_locks WHERE pid = :p AND NOT granted")
    while time.monotonic() < limite:
        async with engine.connect() as conexion:
            if await conexion.scalar(consulta, {"p": pid}):
                return
        await asyncio.sleep(0.05)
    raise AssertionError("la segunda conexión nunca quedó esperando un candado")


async def _escena(una: AsyncSession) -> tuple[UUID, UUID]:
    miembro = await socio(una, consentido=True)
    medicion = await alta(una, SYSTEM_USER_ID, miembro.id)
    una.expunge_all()
    return miembro.id, medicion.id


async def _cuenta_anuladas(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM athletes.body_metrics WHERE voided_at IS NOT NULL")
        )
        or 0
    )


async def test_dos_anulaciones_a_la_vez_una_200_y_la_otra_409_nunca_500(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    """Prueba el candado del SOCIO: la primera anulación lo toma y no confirma; la segunda queda
    esperando en `lock_member` (visible en `pg_locks`) y, al confirmar la primera, lee la fila ya
    anulada y recibe 409 (nunca el 500 del trigger). El candado de la fila y la relectura fresca
    tienen sus propias pruebas más abajo: esta pasaría aunque faltaran."""
    una, otra = dos_sesiones
    member_id, metric_id = await _escena(una)
    pid = int(await otra.scalar(text("SELECT pg_backend_pid()")) or 0)
    primera = await _anular(una, member_id, metric_id)  # candado tomado, sin confirmar
    assert primera.voided_at is not None

    contraria = asyncio.create_task(_anular(otra, member_id, metric_id))
    try:
        try:
            await _esperando_candado(engine, pid)
            assert not contraria.done(), "la segunda anulación debe esperar a la primera"
        finally:
            await una.commit()  # nunca dejar el candado tomado
        resultado = (await asyncio.wait_for(asyncio.gather(contraria, return_exceptions=True), 30))[
            0
        ]
    finally:
        if not contraria.done():
            contraria.cancel()
        await asyncio.gather(contraria, return_exceptions=True)
        await otra.rollback()
    assert isinstance(resultado, DomainError), resultado
    assert (resultado.status, resultado.code) == (409, "metric_already_voided")
    assert await _cuenta_anuladas(una) == 1


async def test_la_fila_se_bloquea_con_for_update_aunque_nadie_tome_el_candado_del_socio(
    engine: AsyncEngine, dos_sesiones: tuple[AsyncSession, AsyncSession]
) -> None:
    """Prueba el `FOR UPDATE`: otra conexión retiene la fila en crudo (como la rotación de llaves,
    que no toma el candado del socio) y la anulación, con `lock_timeout` de 200 ms, falla EN la
    lectura de la fila con un error que `translate_busy` convierte en 503 `busy`. Sin
    `with_for_update` la lectura pasaría y el error llegaría después, en el UPDATE."""
    una, otra = dos_sesiones
    member_id, metric_id = await _escena(una)
    async with engine.connect() as ajena:
        await ajena.execute(
            text("SELECT id FROM athletes.body_metrics WHERE id = :i FOR UPDATE"), {"i": metric_id}
        )
        await otra.execute(text("SET LOCAL lock_timeout = '200ms'"))

        with pytest.raises(DBAPIError) as e:
            await _anular(otra, member_id, metric_id)

        await ajena.rollback()
    await otra.rollback()
    assert translate_busy(e.value) is not None
    assert "FOR UPDATE" in (e.value.statement or ""), e.value.statement
    assert await _cuenta_anuladas(una) == 0


async def test_una_copia_vieja_en_la_sesion_no_engana_la_anulacion(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    """Prueba `populate_existing`: la sesión ya tiene la medición cargada SIN anular; otra
    conexión la anula y confirma; anular de nuevo SIN `expunge_all` debe leer la fila fresca y
    dar 409 (con la copia vieja intentaría anular otra vez y chocaría con el trigger)."""
    una, otra = dos_sesiones
    member_id, metric_id = await _escena(una)
    vieja = await una.scalar(select(BodyMetric).where(BodyMetric.id == metric_id))
    assert vieja is not None and vieja.voided_at is None
    await _anular(otra, member_id, metric_id)
    await otra.commit()

    with pytest.raises(MetricAlreadyVoided):
        await _anular(una, member_id, metric_id)

    await una.rollback()
    assert await _cuenta_anuladas(una) == 1
