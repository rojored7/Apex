"""Sesión de solo lectura de la capa de aplicación del CLI (`seed/`, `imports/`; S4B-B1).

`close()` no descarta las operaciones de índice que la bitácora `crypto_ops` ya acumuló en el
proceso, y el siguiente commit las escribiría: una búsqueda por documento de una corrida sin
cambios dejaría filas nuevas. Por eso termina con `rollback()` explícito, que sí las descarta.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def read_only_session(session_factory: Any) -> AsyncIterator[Any]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
