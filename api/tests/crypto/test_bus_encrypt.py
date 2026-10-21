"""`bus.encrypt` y `bus.decrypt` con llaves reales en `db_test` (US-025 T10)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import bus
from app.core.crypto.blob import parse_blob
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.models import CryptoKey
from app.core.crypto.registry import REGISTRY

CLASES = [n for n, s in REGISTRY.items() if s.encrypt]


@pytest.mark.parametrize("data_class", CLASES)
def test_ida_y_vuelta_por_clase(bus_listo: Keyring, data_class: str) -> None:
    record_id = uuid4()
    aad = bus.aad_for(record_id)
    blob = bus.encrypt(data_class, "1020304 Ñandú".encode(), aad)
    assert bus.decrypt(blob, aad) == "1020304 Ñandú".encode()


def test_aad_for_es_el_uuid_canonico() -> None:
    assert bus.aad_for(uuid4()).isascii()
    from uuid import UUID

    assert bus.aad_for(UUID("ABCDEF01-0000-0000-0000-000000000000")) == (
        b"abcdef01-0000-0000-0000-000000000000"
    )


def test_el_blob_tiene_cinco_partes_y_dos_cifrados_difieren(bus_listo: Keyring) -> None:
    aad = bus.aad_for(uuid4())
    a = bus.encrypt("member.document", b"1020304", aad)
    b = bus.encrypt("member.document", b"1020304", aad)
    assert a != b
    partes = parse_blob(a)
    assert partes.version == "apx1" and partes.alg == "A256GCM"
    assert a.split(".")[1] == str(bus_listo.active_for("encrypt", "member.document").key_id)
    assert b"1020304" not in a.encode()


def test_aad_de_otro_registro_y_ciphertext_alterado(bus_listo: Keyring) -> None:
    aad = bus.aad_for(uuid4())
    blob = bus.encrypt("member.document", b"1020304", aad)
    with pytest.raises(CryptoError) as otro:
        bus.decrypt(blob, bus.aad_for(uuid4()))
    partes = blob.split(".")
    partes[4] = partes[4][:-2] + ("AA" if partes[4][-2:] != "AA" else "BB")
    with pytest.raises(CryptoError) as alterado:
        bus.decrypt(".".join(partes), aad)
    # Mismo código y mismo mensaje: no se distingue AAD de alteración (sin oráculo).
    assert otro.value.code == alterado.value.code == "decrypt_failed"
    assert str(otro.value) == str(alterado.value)


def test_clase_desconocida(bus_listo: Keyring) -> None:
    with pytest.raises(CryptoError) as excinfo:
        bus.encrypt("member.foo", b"x", bus.aad_for(uuid4()))
    assert excinfo.value.code == "unknown_data_class"


async def test_decrypt_only_descifra_y_retired_no(
    bus_listo: Keyring, session: AsyncSession
) -> None:
    aad = bus.aad_for(uuid4())
    blob = bus.encrypt("member.phone", b"3001234567", aad)
    llave = await session.scalar(
        select(CryptoKey).where(
            CryptoKey.purpose == "encrypt", CryptoKey.data_class == "member.phone"
        )
    )
    assert llave is not None
    llave.state = "decrypt_only"
    llave.rotated_at = datetime(2026, 10, 21, tzinfo=UTC)
    await session.flush()
    await bus_listo.refresh_if_stale(session, bus_listo.provider)
    assert bus.decrypt(blob, aad) == b"3001234567"

    llave.state = "retired"
    await session.flush()
    await bus_listo.refresh_if_stale(session, bus_listo.provider)
    with pytest.raises(CryptoError) as excinfo:
        bus.decrypt(blob, aad)
    assert excinfo.value.code == "key_retired"


def test_sin_keyring_el_bus_no_esta_disponible() -> None:
    from app.core.crypto.keyring import configure_keyring

    configure_keyring(None)
    with pytest.raises(CryptoError) as excinfo:
        bus.encrypt("member.document", b"x", bus.aad_for(uuid4()))
    assert excinfo.value.code == "crypto_unavailable"
