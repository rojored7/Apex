"""Concurrencia de `sign_latest` con commit real (S6-A1; S6-D3: `pg_advisory_xact_lock(4_270_004)`).

Aparte de `test_sign_latest.py` porque `dos_sesiones` no se combina con la fixture `session`
(su transacción externa retiene candados) y aquel módulo usa `firmador` en todas sus pruebas.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import audit_sign
from app.core.audit_sign import AuditSignature
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from tests.conftest import LIMPIAR_SIGNATURES
from tests.crypto.conftest import fila_sign, limpiar_llaves_con_commit
from tests.factories import audit_chain
from tests.factories.triggers import disable_user_sql, rearm_always_sql


@pytest.fixture
async def bus_confirmado(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[Keyring]:
    """Llaves del bus con commit real (el keyring del proceso lo comparten las dos sesiones)."""
    await limpiar_llaves_con_commit(engine)
    configure_keyring(None)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as sesion:
            with actor_scope(SYSTEM_USER_ID):
                keyring = await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)
                await fila_sign(sesion, proveedor_local)
                await keyring.load_all(sesion, lambda _n: proveedor_local)
            await sesion.commit()
        yield keyring
    finally:
        configure_keyring(None)
        async with (
            engine.begin() as conexion
        ):  # firmas antes que llaves (FK); y las ops de la prueba
            await conexion.execute(text(LIMPIAR_SIGNATURES))
            await conexion.execute(text(disable_user_sql("crypto.crypto_ops")))
            await conexion.execute(text("DELETE FROM crypto.crypto_ops"))
            await conexion.execute(text(rearm_always_sql("crypto.crypto_ops")))
        await limpiar_llaves_con_commit(engine)


async def test_dos_sesiones_firman_una_sola_fila_bajo_el_candado_4270004(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, engine: AsyncEngine
) -> None:
    primera, segunda = dos_sesiones
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_SIGNATURES))
    await audit_chain.make_audit_chain(primera, 4)
    assert audit_sign.AUDIT_SIGN_LOCK_KEY == 4_270_004

    async def firmar(sesion: AsyncSession) -> str:
        with actor_scope(SYSTEM_USER_ID):
            salida = await audit_sign.sign_latest(sesion)
            await sesion.commit()
        return salida.kind

    tipos = await asyncio.gather(firmar(primera), firmar(segunda))

    assert sorted(tipos) == ["nothing_new", "signed"]
    async with engine.connect() as conexion:
        assert await conexion.scalar(select(func.count()).select_from(AuditSignature)) == 1


async def test_la_segunda_firma_tiene_signed_at_y_through_seq_mayores(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, engine: AsyncEngine
) -> None:
    """H2: `now()` es el inicio de la transacción; una sesión abierta antes de la primera firma
    firmaría con una hora anterior. `signed_at` sale de `clock_timestamp()` tras la firma."""
    primera, segunda = dos_sesiones
    async with engine.begin() as conexion:
        await conexion.execute(text(LIMPIAR_SIGNATURES))
    await audit_chain.make_audit_chain(primera, 3)
    await segunda.execute(select(1))  # la transacción de `segunda` empieza ahora
    with actor_scope(SYSTEM_USER_ID):
        await audit_sign.sign_latest(primera)
        await primera.commit()
    await audit_chain.make_audit_chain(primera, 2)

    with actor_scope(SYSTEM_USER_ID):
        salida = await audit_sign.sign_latest(segunda)
        await segunda.commit()

    assert (salida.kind, salida.through_seq) == ("signed", 5)
    async with engine.connect() as conexion:
        filas = (
            await conexion.execute(
                select(AuditSignature.through_seq, AuditSignature.signed_at).order_by(
                    AuditSignature.through_seq
                )
            )
        ).all()
    assert [f.through_seq for f in filas] == [3, 5]
    assert filas[1].signed_at > filas[0].signed_at
