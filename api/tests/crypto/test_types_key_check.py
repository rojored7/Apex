"""Verificación de llave vigente en el flush (US-028 T6, requerida por US-030)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.secret import Secret
from app.core.crypto.types import install_crypto_type_listeners
from tests.crypto.models_fixture import SCHEMA, CryptoTestPerson


@pytest.fixture
async def db(bus_listo: Keyring, session: AsyncSession) -> AsyncIterator[AsyncSession]:
    install_crypto_type_listeners()
    await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    await session.run_sync(
        lambda s: CryptoTestPerson.__table__.create(s.connection(), checkfirst=True)
    )
    with actor_scope(SYSTEM_USER_ID):
        yield session


async def test_con_la_llave_vigente_pasa(db: AsyncSession) -> None:
    db.add(CryptoTestPerson(name="Ana", document=Secret.from_plain("1")))
    await db.flush()


async def test_una_rotacion_desde_otra_sesion_hace_fallar_el_flush(
    db: AsyncSession, bus_listo: Keyring, proveedor_local: LocalFileProvider
) -> None:
    # Simula US-030 desde "otro proceso": la activa pasa a decrypt_only y entra una v2,
    # sin que el keyring de este proceso se haya enterado.
    vieja = bus_listo.active_for("encrypt", "member.document")
    fila = await db.get(CryptoKey, vieja.key_id)
    assert fila is not None
    fila.state = "decrypt_only"
    fila.rotated_at = datetime(2026, 10, 21, tzinfo=UTC)
    db.add(
        CryptoKey(
            purpose="encrypt",
            data_class="member.document",
            algorithm="A256GCM",
            provider="local",
            version=2,
            state="active",
            wrapped_material=await proveedor_local.wrap(b"\x02" * 32),
            created_by=SYSTEM_USER_ID,
        )
    )
    await db.flush()
    db.add(CryptoTestPerson(name="Ana", document=Secret.from_plain("1")))
    with pytest.raises(CryptoError) as excinfo:
        await db.flush()
    assert excinfo.value.code == "crypto_key_changed"
    await db.rollback()
