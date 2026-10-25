"""Fixtures de `tests/memberships` (plan del Sprint 3, sección 2, bloque B1).

- `memberships_service` se importa al nivel del módulo (blueprint, reglas de pruebas 2):
  `restaurar_bus` restaura el bus al terminar cada prueba y una suscripción hecha por un import
  perezoso dentro de una prueba se perdería.
- `bus_confirmado`: copia de `tests/members/conftest.py`. Las llaves del bus con commit real, para
  las pruebas de concurrencia con `dos_sesiones` (dos conexiones que no ven el savepoint de
  `bus_listo`): el flush de un socio cifra y lee la llave vigente con `FOR SHARE` en
  `crypto_keys`. Al salir borra las llaves y las filas de `crypto_ops` escritas desde que empezó.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.modules.memberships import service as memberships_service  # noqa: F401
from tests.conftest import LIMPIAR_LLAVES


async def _limpiar(engine: AsyncEngine, desde: object) -> None:
    async with engine.begin() as conexion:
        for sql in LIMPIAR_LLAVES:
            await conexion.execute(text(sql))
        await conexion.execute(text("ALTER TABLE crypto.crypto_ops DISABLE TRIGGER USER"))
        await conexion.execute(text("DELETE FROM crypto.crypto_ops WHERE at >= :t"), {"t": desde})
        await conexion.execute(text("ALTER TABLE crypto.crypto_ops ENABLE TRIGGER USER"))


@pytest.fixture
async def bus_confirmado(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Keyring]:
    async with engine.connect() as conexion:
        desde = await conexion.scalar(text("SELECT clock_timestamp()"))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as sesion:
        for sql in LIMPIAR_LLAVES:
            await sesion.execute(text(sql))
        configure_keyring(None)
        with actor_scope(SYSTEM_USER_ID):
            keyring = await ensure_keys(sesion, proveedor_local)
            await sesion.commit()
    try:
        yield keyring
    finally:
        configure_keyring(None)
        await _limpiar(engine, desde)
