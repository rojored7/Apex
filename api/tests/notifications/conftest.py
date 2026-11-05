"""Fixtures de `tests/notifications` (S5-B7). # Rojo B7

`listo`: el bus de criptografía con llaves (`bus_listo`) y el reloj congelado en `T0`
(2026-10-21 10:00 en Bogotá). Los socios de las pruebas de avisos se cifran y los avisos se
generan o se leen con ese "hoy".
"""

from __future__ import annotations

import pytest

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring


@pytest.fixture
def listo(bus_listo: Keyring, reloj: FrozenClock) -> Keyring:
    return bus_listo


from collections.abc import AsyncIterator  # noqa: E402

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker  # noqa: E402

from app.core.audit import AuditEntry  # noqa: E402
from tests.conftest import limpiar_tras_dos_sesiones  # noqa: E402
from tests.members.conftest import bus_confirmado  # noqa: E402,F401  (S5-D223: llaves con commit real)


@pytest.fixture
async def fabrica(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """S5-B8: fábrica con commit real (el envío abre sesiones cortas propias); al salir borra lo
    que quedó, como `dos_sesiones`."""
    async with engine.connect() as conexion:
        ultima = await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0)))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await limpiar_tras_dos_sesiones(engine, ultima or 0)
