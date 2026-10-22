"""Fixtures de `tests/members` (S2-B7).

`bus_confirmado`: las llaves del bus con commit real, para las pruebas de concurrencia con
`dos_sesiones` (dos conexiones que no ven el savepoint de `bus_listo`). Antes de cifrar, el flush
lee la llave vigente con `SELECT ... FOR SHARE` en `crypto_keys`; por eso las llaves deben estar
confirmadas. Al salir borra las llaves y las filas de `crypto_ops` que se escribieron desde que
empezó, y descarga el keyring: la base queda como al inicio de la sesión de pruebas.
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
