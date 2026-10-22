"""Ayudas del bus para las pruebas de `tests/crypto`.

`proveedor_local`, `sin_llaves` y `bus_listo` viven en `tests/conftest.py` desde S2-B1
(S2-D19): las usan también `tests/core`, `tests/settings` y los módulos siguientes.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import LIMPIAR_LLAVES


async def limpiar_llaves_con_commit(engine: AsyncEngine) -> None:
    """Solo en pruebas: borra las llaves con los triggers apagados y confirma."""
    async with engine.begin() as conn:
        for sql in LIMPIAR_LLAVES:
            await conn.execute(text(sql))
