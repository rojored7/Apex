"""`ensure_keys`: una DEK y una llave de índice por clase, idempotente (US-025 T11, US-026 T4)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.registry import REGISTRY
from tests.crypto.conftest import limpiar_llaves_con_commit

CIFRADO = sorted(n for n, s in REGISTRY.items() if s.encrypt)
INDICE = sorted(n for n, s in REGISTRY.items() if s.index_kind)


async def _llaves(session: AsyncSession) -> list[CryptoKey]:
    return list(
        (
            await session.scalars(
                select(CryptoKey).order_by(CryptoKey.purpose, CryptoKey.data_class)
            )
        ).all()
    )


async def test_base_vacia_crea_una_llave_por_clase(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local)
    llaves = await _llaves(sin_llaves)
    assert [(k.purpose, k.data_class) for k in llaves] == [
        *[("encrypt", c) for c in CIFRADO],
        *[("index", c) for c in INDICE],
    ]
    for llave in llaves:
        assert llave.state == "active" and llave.version == 1 and llave.provider == "local"
        assert llave.created_by == SYSTEM_USER_ID
        assert llave.algorithm == ("A256GCM" if llave.purpose == "encrypt" else "HMAC-SHA256")
        abierta = keyring.get(llave.id)
        assert abierta is not None and len(abierta.material) == 32
        assert bytes(abierta.material) != llave.wrapped_material
        assert bytes(abierta.material) not in llave.wrapped_material
        assert llave.wrapped_material.startswith(b"apxw1")
    assert "apxw1" not in repr(keyring) and repr(keyring).count("material") == 0


async def test_segundo_arranque_no_crea_mas(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        primero = await ensure_keys(sin_llaves, proveedor_local)
        segundo = await ensure_keys(sin_llaves, proveedor_local)
    total = await sin_llaves.scalar(select(func.count()).select_from(CryptoKey))
    assert total == len(CIFRADO) + len(INDICE)
    assert {k.key_id for k in primero.keys()} == {k.key_id for k in segundo.keys()}


async def test_una_llave_creada_por_otra_sesion_se_carga_con_refresh(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        keyring = await ensure_keys(sin_llaves, proveedor_local)
    nueva = CryptoKey(
        purpose="encrypt",
        data_class="member.document",
        algorithm="A256GCM",
        provider="local",
        version=2,
        state="decrypt_only",
        wrapped_material=await proveedor_local.wrap(b"\x01" * 32),
        created_by=SYSTEM_USER_ID,
    )
    sin_llaves.add(nueva)
    await sin_llaves.flush()
    assert keyring.get(nueva.id) is None
    assert await keyring.refresh_if_stale(sin_llaves, proveedor_local) is True
    cargada = keyring.get(nueva.id)
    assert cargada is not None and bytes(cargada.material) == b"\x01" * 32
    assert await keyring.refresh_if_stale(sin_llaves, proveedor_local) is False


@pytest.fixture
async def motor_sin_llaves(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    await limpiar_llaves_con_commit(engine)
    configure_keyring(None)
    try:
        yield engine
    finally:
        await limpiar_llaves_con_commit(engine)
        configure_keyring(None)


async def test_dos_arranques_concurrentes_dejan_una_sola_llave_por_clase(
    motor_sin_llaves: AsyncEngine, proveedor_local: LocalFileProvider
) -> None:
    fabrica = async_sessionmaker(motor_sin_llaves, expire_on_commit=False)

    async def arrancar() -> Keyring:
        async with fabrica() as session, session.begin():
            with actor_scope(SYSTEM_USER_ID):
                return await ensure_keys(session, proveedor_local)

    a, b = await asyncio.gather(arrancar(), arrancar())
    async with fabrica() as session:
        llaves = await _llaves(session)
    assert len(llaves) == len(CIFRADO) + len(INDICE)
    assert len({(k.purpose, k.data_class) for k in llaves}) == len(llaves)
    assert {k.key_id for k in a.keys()} == {k.key_id for k in b.keys()} == {k.id for k in llaves}
