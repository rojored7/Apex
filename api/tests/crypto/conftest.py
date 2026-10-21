"""Fixtures del bus: proveedor local con las llaves de la sesión y keyring cargado."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.cli import key_paths_in
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider

LIMPIAR_LLAVES = (
    "ALTER TABLE crypto.crypto_keys DISABLE TRIGGER USER",
    "DELETE FROM crypto.crypto_keys",
    "ALTER TABLE crypto.crypto_keys ENABLE TRIGGER USER",
)


@pytest.fixture
def proveedor_local(claves_prueba: Path) -> LocalFileProvider:
    rutas = key_paths_in(claves_prueba)
    return LocalFileProvider(rutas.kek, rutas.signing_key)


async def limpiar_llaves_con_commit(engine: AsyncEngine) -> None:
    """Solo en pruebas: borra las llaves con los triggers apagados y confirma."""
    async with engine.begin() as conn:
        for sql in LIMPIAR_LLAVES:
            await conn.execute(text(sql))


@pytest.fixture
async def sin_llaves(session: AsyncSession) -> AsyncSession:
    """Tabla `crypto_keys` vacía dentro del savepoint de la prueba (se revierte)."""
    for sql in LIMPIAR_LLAVES:
        await session.execute(text(sql))
    configure_keyring(None)
    return session


@pytest.fixture
async def bus_listo(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> AsyncIterator[Keyring]:
    """`ensure_keys` sobre base vacía: DEK y llaves de índice creadas y keyring cargado."""
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local)
    try:
        yield keyring
    finally:
        configure_keyring(None)
