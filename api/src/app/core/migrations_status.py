"""Estado público de las migraciones para `/health` (US-118; S4B-D27, S4B-D60).

`migrations_health()` lee la única fila de `public.alembic_version` y la compara con el `head` del
código, que `main.py` calcula una vez al crear la app y entrega con `configure_migrations`
(`ScriptDirectory.from_config(...)`; este archivo nunca importa `app.main` ni módulos):

- `ok`: la base está en `head`.
- `mismatch`: hay una revisión distinta de `head`, conocida (la base va detrás: `behind`) o
  desconocida (la base va delante o viene de otro árbol: `unknown_revision`). El cuerpo público no
  distingue una de otra ni nombra la revisión; el log sí (solo el identificador de la revisión,
  recortado, nunca la URL ni la contraseña).
- `unknown`: no se pudo leer (base caída, más lenta que `DB_TIMEOUT_S`, o 0 o 2+ filas).

Nunca lanza. El SQL es una constante sin parámetros (S4B-D60).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from sqlalchemy import text

from app.core.db import get_engine

logger = logging.getLogger("app.migrations_status")

ALEMBIC_VERSION_SQL: Final = "SELECT version_num FROM public.alembic_version"
"""Única sentencia del archivo: constante, sin parámetros que construir (S4B-D60)."""

DB_TIMEOUT_S: Final = 2.5
"""Tope de la lectura: con la base caída `/health` responde en menos de 3 s."""

_MAX_REVISION_LOG: Final = 64

_head: str | None = None
_known: frozenset[str] = frozenset()


def configure_migrations(head: str, known: frozenset[str]) -> None:
    """Fija `head` y las revisiones conocidas (una vez, al crear la app)."""
    global _head, _known
    _head = head
    _known = frozenset(known)


def _para_log(revision: str) -> str:
    """Identificador de revisión apto para el log: recortado y sin caracteres de control."""
    limpio = "".join(c if c.isprintable() else "?" for c in revision[:_MAX_REVISION_LOG])
    return limpio


async def _leer_filas() -> list[str]:
    async with asyncio.timeout(DB_TIMEOUT_S), get_engine().connect() as conexion:
        resultado = await conexion.execute(text(ALEMBIC_VERSION_SQL))
        return [str(fila[0]) for fila in resultado.all()]


async def migrations_health() -> str:
    """`ok | mismatch | unknown`; nunca lanza y nunca devuelve la revisión."""
    if _head is None:
        logger.warning("migrations: no se configuró head (configure_migrations)")
        return "unknown"
    try:
        filas = await _leer_filas()
    except Exception:
        logger.warning("migrations: no se pudo leer alembic_version")
        return "unknown"
    if len(filas) != 1:
        logger.warning("migrations: alembic_version tiene %d filas (se esperaba 1)", len(filas))
        return "unknown"
    actual = filas[0]
    if actual == _head:
        return "ok"
    motivo = "behind" if actual in _known else "unknown_revision"
    logger.warning(
        "migrations: la base no está en head (%s): actual=%s head=%s",
        motivo,
        _para_log(actual),
        _para_log(_head),
    )
    return "mismatch"
