"""Apoyo de las pruebas de la verificación de la cadena (plan del Sprint 4A, sección 2, bloque B3).

- `VERIFY = "/api/v1/audit/verify"` y `VERIFY_LAST`; `CAMPOS_RESULTADO` (forma exacta de
  `VerifyResultOut`) y `CLAVES_AFTER` (las de la fila `verify` de la cadena, S4A-D12 y S4A-D43).
- `candado_libre(url)`: desde una conexión asyncpg independiente (otro proceso, para PostgreSQL),
  `pg_try_advisory_lock(4_270_003)`; si lo obtiene lo suelta y devuelve `True`. Así una prueba
  sabe que ninguna conexión (tampoco una devuelta al pool) se quedó con el candado.
- `EspiaDeConexiones`: envuelve `AsyncConnection.execution_options` e `invalidate` a nivel de
  clase y anota qué conexiones pasaron a `AUTOCOMMIT` y cuáles se invalidaron (H-2, S4A-D44).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.audit_verify import AUDIT_VERIFY_LOCK_KEY

VERIFY: Final = "/api/v1/audit/verify"
VERIFY_LAST: Final = "/api/v1/audit/verify/last"
CAMPOS_RESULTADO: Final = frozenset(
    {
        "ok",
        "rows_checked",
        "through_seq",
        "broken_at_seq",
        "started_at",
        "finished_at",
        "triggered_by",
        "source",
    }
)
CLAVES_AFTER: Final = frozenset(
    {
        "ok",
        "rows_checked",
        "broken_at_seq",
        "through_seq",
        "through_hash",
        "started_at",
        "finished_at",
        "source",
    }
)


def dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def candado_libre(url: str) -> bool:
    """`True` si una conexión independiente obtiene (y suelta) el candado `4_270_003`."""
    conexion = await asyncpg.connect(dsn(url))
    try:
        obtenido = bool(
            await conexion.fetchval("SELECT pg_try_advisory_lock($1)", AUDIT_VERIFY_LOCK_KEY)
        )
        if obtenido:
            await conexion.fetchval("SELECT pg_advisory_unlock($1)", AUDIT_VERIFY_LOCK_KEY)
        return obtenido
    finally:
        await conexion.close()


@dataclass
class EspiaDeConexiones:
    """Conexiones (por `id`) que pidieron `AUTOCOMMIT` y que se invalidaron."""

    autocommit: list[int] = field(default_factory=list)
    invalidadas: list[int] = field(default_factory=list)

    def instalar(self, monkeypatch: pytest.MonkeyPatch) -> EspiaDeConexiones:
        original_opciones = AsyncConnection.execution_options
        original_invalidar = AsyncConnection.invalidate
        espia = self

        async def opciones(conn: AsyncConnection, **opt: Any) -> AsyncConnection:
            if opt.get("isolation_level") == "AUTOCOMMIT":
                espia.autocommit.append(id(conn))
            return await original_opciones(conn, **opt)

        async def invalidar(conn: AsyncConnection, exception: BaseException | None = None) -> None:
            espia.invalidadas.append(id(conn))
            await original_invalidar(conn, exception)

        monkeypatch.setattr(AsyncConnection, "execution_options", opciones)
        monkeypatch.setattr(AsyncConnection, "invalidate", invalidar)
        return self

    def autocommit_invalidadas(self) -> set[int]:
        """Conexiones que fueron `AUTOCOMMIT` y luego se invalidaron (la del candado)."""
        return set(self.autocommit) & set(self.invalidadas)
