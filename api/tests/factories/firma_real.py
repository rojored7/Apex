"""Escenarios de firma con commit real para `sign_audit` y `sign-audit` (S6-A2; S6-D8, D42, D81).

- `llaves_de_firma(engine, proveedor, ...)`: administrador de contexto. Deja en la base, ya
  confirmadas, las DEK del bus (`ensure_keys`) y la fila `sign` de `audit.signature` (`fila_sign`)
  con la clave pública del proveedor; el keyring del proceso queda en `None` (el job o el comando
  lo cargan por `recovery.try_load`/`crypto_runtime`). Al salir borra firmas, llaves y `crypto_ops`.
- `cadena(fabrica, n, ...)`: agrega `n` filas válidas a `audit.audit_log` con commit y devuelve
  `(primer_seq, ultimo_seq)`; con `reloj` las fecha con ese reloj (para la firma «atrasada»).
- `firmas(fabrica)`: filas crudas de `audit.signatures` por `through_seq`.
- `candado_libre(engine)`: `True` si el candado `4_270_004` de la firma está libre.
- `ops_de_firma(fabrica)`: pares `(verb, result)` de `crypto_ops` de `audit.signature`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.audit_sign import AUDIT_SIGN_LOCK_KEY
from app.core.clock import Clock, reset_clock, set_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoOp
from tests.conftest import LIMPIAR_SIGNATURES
from tests.crypto.conftest import fila_sign, limpiar_llaves_con_commit
from tests.factories import audit_chain
from tests.factories.signatures import firmas as _firmas
from tests.factories.triggers import disable_user_sql, rearm_always_sql

Fabrica = async_sessionmaker[AsyncSession]
CLASE = "audit.signature"


async def _borrar_ops(engine: AsyncEngine) -> None:
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_SIGNATURES))  # firmas antes que llaves (FK)
        await conexion.execute(text(disable_user_sql("crypto.crypto_ops")))
        await conexion.execute(text("DELETE FROM crypto.crypto_ops"))
        await conexion.execute(text(rearm_always_sql("crypto.crypto_ops")))


@asynccontextmanager
async def llaves_de_firma(
    engine: AsyncEngine,
    proveedor: LocalFileProvider,
    *,
    con_fila_sign: bool = True,
    public_key: str | None = None,
) -> AsyncIterator[Fabrica]:
    await limpiar_llaves_con_commit(engine)
    configure_keyring(None)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as sesion:
            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor, lambda _n: proveedor)
                if con_fila_sign:
                    await fila_sign(sesion, proveedor, public_key=public_key)
            await sesion.commit()
        configure_keyring(None)
        yield fabrica
    finally:
        configure_keyring(None)
        await _borrar_ops(engine)
        await limpiar_llaves_con_commit(engine)


@contextmanager
def _con_reloj(reloj: Clock | None) -> Any:
    token = set_clock(reloj) if reloj is not None else None
    try:
        yield
    finally:
        if token is not None:
            reset_clock(token)


async def cadena(fabrica: Fabrica, n: int, *, reloj: Clock | None = None) -> tuple[int, int]:
    """`n` filas válidas con commit; `(primer_seq, ultimo_seq)`."""
    with _con_reloj(reloj):
        async with fabrica() as sesion:
            ultimo = await audit_chain.make_audit_chain(sesion, n)
            await sesion.commit()
    return ultimo - n + 1, ultimo


async def alterar(fabrica: Fabrica, seq: int) -> None:
    """Cambia `after` de la fila `seq` (sin recalcular el hash) con commit."""
    async with fabrica() as sesion:
        await audit_chain.tamper_row(sesion, seq, "after", {"n": seq, "alterado": True})
        await sesion.commit()


async def firmas(fabrica: Fabrica) -> list[Any]:
    async with fabrica() as sesion:
        return await _firmas(sesion)


async def candado_libre(engine: AsyncEngine) -> bool:
    async with engine.connect() as conexion:
        tomado = await conexion.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": AUDIT_SIGN_LOCK_KEY}
        )
        if tomado:
            await conexion.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": AUDIT_SIGN_LOCK_KEY})
        return bool(tomado)


async def ops_de_firma(fabrica: Fabrica) -> list[tuple[str, str]]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(CryptoOp).where(CryptoOp.data_class == CLASE).order_by(CryptoOp.at)
        )
        return [(f.verb, f.result) for f in filas]
