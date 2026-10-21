"""`crypto_ops` con transacciones reales (US-029 T10): una fila por operación, lotes,
errores que sobreviven al rollback, sin material ni blobs, y commit sin actor que falla."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, MissingActorError, actor_scope, batch_scope
from app.core.crypto import bus
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoOp
from app.core.crypto.oplog import install_oplog_listeners, reset_buffer
from tests.crypto.conftest import limpiar_llaves_con_commit

ACTOR = UUID(int=42)
CLARO = b"1020304-texto-claro"


async def _limpiar_ops(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE crypto.crypto_ops DISABLE TRIGGER USER"))
        await conn.execute(text("DELETE FROM crypto.crypto_ops"))
        await conn.execute(text("ALTER TABLE crypto.crypto_ops ENABLE TRIGGER USER"))


@pytest.fixture
async def uow(
    engine: AsyncEngine, proveedor_local: LocalFileProvider
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sesiones que confirman de verdad; llaves creadas por `ensure_keys` en su propio commit."""
    install_oplog_listeners()
    await limpiar_llaves_con_commit(engine)
    await _limpiar_ops(engine)
    reset_buffer()
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as session, session.begin():
        with actor_scope(SYSTEM_USER_ID):
            await ensure_keys(session, proveedor_local)
    await _limpiar_ops(engine)  # las filas wrap/unwrap del arranque no cuentan aquí
    try:
        yield fabrica
    finally:
        reset_buffer()
        configure_keyring(None)
        await _limpiar_ops(engine)
        await limpiar_llaves_con_commit(engine)


@asynccontextmanager
async def tx(
    fabrica: async_sessionmaker[AsyncSession], actor: UUID | None = None, lote: UUID | None = None
) -> AsyncIterator[AsyncSession]:
    """Transacción real con actor y lote fijados antes de abrir la sesión."""
    with ExitStack() as pila:
        if actor is not None:
            pila.enter_context(actor_scope(actor))
        if lote is not None:
            pila.enter_context(batch_scope(lote))
        async with fabrica() as session, session.begin():
            yield session


async def _filas(fabrica: async_sessionmaker[AsyncSession]) -> list[CryptoOp]:
    async with fabrica() as session:
        return list(
            (await session.scalars(select(CryptoOp).order_by(CryptoOp.at, CryptoOp.verb))).all()
        )


async def test_cifrar_deja_una_fila_encrypt_con_el_actor(
    uow: async_sessionmaker[AsyncSession],
) -> None:
    record_id = uuid4()
    async with tx(uow, ACTOR) as _session:
        blob = bus.encrypt("member.document", CLARO, bus.aad_for(record_id))
    filas = await _filas(uow)
    assert [f.verb for f in filas] == ["encrypt"]
    fila = filas[0]
    assert fila.data_class == "member.document" and fila.result == "ok" and fila.count == 1
    assert fila.key_id == UUID(blob.split(".")[1]) and fila.key_version == 1
    assert fila.record_id == record_id and fila.user_id == ACTOR and fila.created_by == ACTOR
    assert fila.batch_id is None and fila.purpose is None


async def test_500_descifrados_en_batch_dan_una_fila(uow: async_sessionmaker[AsyncSession]) -> None:
    aad = bus.aad_for(uuid4())
    async with tx(uow, ACTOR) as _session:
        blob = bus.encrypt("member.phone", b"3001234567", aad)
        with bus.batch("decrypt", "member.phone") as lote:
            for _ in range(500):
                bus.decrypt(blob, aad, purpose="mask")
    filas = await _filas(uow)
    decrypt = [f for f in filas if f.verb == "decrypt"]
    assert len(decrypt) == 1
    assert decrypt[0].count == 500 and decrypt[0].batch_id == lote.batch_id
    assert decrypt[0].purpose == "mask" and decrypt[0].record_id is None


async def test_error_de_descifrado_sobrevive_al_rollback(
    uow: async_sessionmaker[AsyncSession],
) -> None:
    record_id = uuid4()
    async with tx(uow, ACTOR) as _session:
        blob = bus.encrypt("member.document", CLARO, bus.aad_for(record_id))
    with pytest.raises(CryptoError):
        async with tx(uow, ACTOR) as _session:
            bus.decrypt(blob, bus.aad_for(uuid4()), purpose="reveal", record_id=record_id)
    filas = await _filas(uow)
    errores = [f for f in filas if f.result == "error"]
    assert len(errores) == 1
    assert errores[0].verb == "decrypt" and errores[0].record_id == record_id
    assert errores[0].purpose == "reveal" and errores[0].user_id == ACTOR


async def test_ninguna_fila_contiene_blob_ni_texto(uow: async_sessionmaker[AsyncSession]) -> None:
    aad = bus.aad_for(uuid4())
    async with tx(uow, ACTOR) as session:
        blob = bus.encrypt("member.email", CLARO, aad)
        bus.decrypt(blob, aad, purpose="mask")
        bus.blind_index("member.email", "ana@mail.com")
    async with uow() as session:
        textos = (
            await session.scalars(text("SELECT row_to_json(o)::text FROM crypto.crypto_ops o"))
        ).all()
    assert textos
    for fila in textos:
        assert blob not in fila and CLARO.decode() not in fila and "ana@mail.com" not in fila
    assert sorted(f.verb for f in await _filas(uow)) == ["decrypt", "encrypt", "index"]


async def test_sin_actor_el_commit_falla(uow: async_sessionmaker[AsyncSession]) -> None:
    from app.core.context import current_actor

    token = current_actor.set(None)
    try:
        with pytest.raises(MissingActorError, match="falta el actor"):
            async with tx(uow) as _session:
                bus.encrypt("member.document", CLARO, bus.aad_for(uuid4()))
    finally:
        current_actor.reset(token)
        reset_buffer()
    assert await _filas(uow) == []


async def test_batch_scope_comparte_el_batch_id(uow: async_sessionmaker[AsyncSession]) -> None:
    lote = uuid4()
    async with tx(uow, SYSTEM_USER_ID, lote) as _session:
        for n in range(3):
            bus.encrypt("member.document", CLARO, bus.aad_for(uuid4()))
            bus.blind_index("member.document", f"10{n}")
    filas = await _filas(uow)
    # Sin `bus.batch` cada operación es una fila (conserva su record_id); todas con el lote.
    assert len(filas) == 6 and {f.batch_id for f in filas} == {lote}
    assert {f.count for f in filas} == {1} and sorted(f.verb for f in filas)[:3] == ["encrypt"] * 3


async def test_update_sobre_crypto_ops_falla(uow: async_sessionmaker[AsyncSession]) -> None:
    async with tx(uow, ACTOR) as session:
        bus.encrypt("member.document", CLARO, bus.aad_for(uuid4()))
    with pytest.raises(DBAPIError, match="append-only"):
        async with tx(uow) as session:
            await session.execute(text("UPDATE crypto.crypto_ops SET result = 'error'"))
    async with uow() as session:
        assert await session.scalar(select(func.count()).select_from(CryptoOp)) == 1


def test_keyring_no_se_toca(uow: async_sessionmaker[AsyncSession]) -> None:
    from app.core.crypto.keyring import current_keyring

    assert isinstance(current_keyring(), Keyring)
