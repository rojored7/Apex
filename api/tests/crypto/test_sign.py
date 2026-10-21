"""`bus.sign` y `bus.verify` con una clase de prueba registrada (US-027 T6; Q27)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.oplog import reset_buffer
from app.core.crypto.registry import REGISTRY, DataClassSpec, override_registry

FIRMA = DataClassSpec("test.signature", False, None, True, "str", ("worker.t.sig",))
OTRA = DataClassSpec("test.other", False, None, True, "str", ("worker.t.other",))


@pytest.fixture
async def bus_firma(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> AsyncIterator[Keyring]:
    with override_registry({**REGISTRY, FIRMA.name: FIRMA, OTRA.name: OTRA}):
        with actor_scope(SYSTEM_USER_ID):
            keyring = await ensure_keys(sin_llaves, proveedor_local)
        try:
            yield keyring
        finally:
            configure_keyring(None)
            reset_buffer()


async def test_firmar_y_verificar(bus_firma: Keyring) -> None:
    firma = await bus.sign("test.signature", b"hash-de-la-cadena")
    assert firma.startswith("apx1.") and len(firma.split(".")) == 4
    assert await bus.verify("test.signature", b"hash-de-la-cadena", firma) is True
    assert await bus.verify("test.signature", b"hash-de-la-cadenA", firma) is False


async def test_firma_mal_formada_y_clase_sin_firma(bus_firma: Keyring) -> None:
    with pytest.raises(CryptoError) as mal:
        await bus.verify("test.signature", b"x", "abc")
    assert mal.value.code == "signature_invalid"
    with pytest.raises(CryptoError) as sin:
        await bus.sign("member.document", b"x")
    assert sin.value.code == "unsupported"


async def test_una_firma_de_otra_clase_no_verifica(bus_firma: Keyring) -> None:
    firma = await bus.sign("test.other", b"datos")
    with pytest.raises(CryptoError) as excinfo:
        await bus.verify("test.signature", b"datos", firma)
    assert excinfo.value.code == "key_missing"


async def test_llave_decrypt_only_y_retired_siguen_verificando(
    bus_firma: Keyring, sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    firma = await bus.sign("test.signature", b"viejo")
    llave = await sin_llaves.scalar(
        select(CryptoKey).where(
            CryptoKey.purpose == "sign", CryptoKey.data_class == "test.signature"
        )
    )
    assert llave is not None and llave.algorithm == "Ed25519"
    assert llave.wrapped_material == b"local:sign-ed25519"
    llave.state = "decrypt_only"
    llave.rotated_at = datetime(2026, 10, 21, tzinfo=UTC)
    await sin_llaves.flush()
    await bus_firma.refresh_if_stale(sin_llaves, proveedor_local)
    assert await bus.verify("test.signature", b"viejo", firma) is True
    llave.state = "retired"
    await sin_llaves.flush()
    await bus_firma.refresh_if_stale(sin_llaves, proveedor_local)
    assert await bus.verify("test.signature", b"viejo", firma) is True
    with pytest.raises(CryptoError):
        await bus.sign("test.signature", b"nuevo")  # sin llave activa


def test_el_bus_no_expone_llaves_privadas() -> None:
    assert not [n for n in dir(bus) if "private" in n.lower() or "kek" in n.lower()]
