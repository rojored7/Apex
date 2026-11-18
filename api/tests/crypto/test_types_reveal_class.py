"""`reveal` rechaza un blob de OTRA clase de dato (S9-V7b, L-3 de seguridad de la revisión V7).

Un blob cuya llave es de otra `data_class` no debe abrirse como el campo que lo contiene: el error
es opaco (`class_mismatch`, sin la clase real ni bytes) y deja una fila `decrypt` con `error` en
`crypto_ops`. Un blob de la MISMA clase sigue valiendo (también con la llave `decrypt_only` de una
rotación: la clase no cambia).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus, oplog
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.secret import Secret
from app.core.crypto.types import install_crypto_type_listeners, reveal
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


async def _persona(db: AsyncSession) -> CryptoTestPerson:
    persona = CryptoTestPerson(name="Ana", document=Secret.from_plain("1020304"))
    db.add(persona)
    await db.flush()
    return persona


async def test_un_blob_de_otra_clase_se_rechaza_con_error_opaco(db: AsyncSession) -> None:
    persona = await _persona(db)
    ajeno = bus.encrypt("member.phone", b"3001234567", bus.aad_for(persona.id))
    persona.document = Secret.from_blob(ajeno)  # la columna es `member.document`

    with pytest.raises(CryptoError) as error:
        reveal(persona, "document", "mask")

    assert error.value.code == "class_mismatch"
    assert "member.phone" not in str(error.value) and "3001234567" not in str(error.value)


async def test_el_rechazo_deja_una_fila_decrypt_con_error(db: AsyncSession) -> None:
    persona = await _persona(db)
    ajeno = bus.encrypt("member.phone", b"3001234567", bus.aad_for(persona.id))
    persona.document = Secret.from_blob(ajeno)
    antes = len(oplog.pending_rows())

    with pytest.raises(CryptoError):
        reveal(persona, "document", "mask")

    nuevas = oplog.pending_rows()[antes:]
    assert [(f.verb, f.result, f.data_class) for f in nuevas] == [
        ("decrypt", "error", "member.phone")
    ]


async def test_un_blob_de_la_misma_clase_sigue_valiendo(db: AsyncSession) -> None:
    persona = await _persona(db)
    propio = bus.encrypt("member.document", b"9988", bus.aad_for(persona.id))
    persona.document = Secret.from_blob(propio)

    assert reveal(persona, "document", "mask") == "9988"
