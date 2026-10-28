"""`Encrypted` y `BlindIndexed` con PostgreSQL real (US-028 T10)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring
from app.core.crypto.secret import Secret
from app.core.crypto.types import install_crypto_type_listeners, reveal
from tests.crypto.models_fixture import SCHEMA, CryptoTestPerson

DOC = "1.020.304"
CONTACTO = {"name": "Ana Pérez", "phone": "3001234567"}


@pytest.fixture
async def db(bus_listo: Keyring, session: AsyncSession) -> AsyncIterator[AsyncSession]:
    install_crypto_type_listeners()
    await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    await session.run_sync(
        lambda s: CryptoTestPerson.__table__.create(s.connection(), checkfirst=True)
    )
    with actor_scope(SYSTEM_USER_ID):
        yield session


def _persona(**cambios: object) -> CryptoTestPerson:
    valores: dict[str, object] = {
        "name": "Ana",
        "document": Secret.from_plain(DOC),
        "phone": Secret.from_plain("+57 300 123 4567"),
        "email": Secret.from_plain(" Ana.Perez@Mail.com "),
        "birth_date": Secret.from_plain(date(2000, 1, 2)),
        "emergency_contact": Secret.from_plain(CONTACTO),
    }
    valores.update(cambios)
    return CryptoTestPerson(**valores)


async def _fila_json(session: AsyncSession, persona_id: UUID) -> str:
    return str(
        await session.scalar(
            text(f"SELECT row_to_json(t)::text FROM {SCHEMA}.crypto_test_person t WHERE id = :id"),  # noqa: S608 - SCHEMA es una constante de prueba
            {"id": persona_id},
        )
    )


async def test_guarda_blobs_e_indices_y_nunca_el_claro(db: AsyncSession) -> None:
    persona = _persona()
    db.add(persona)
    await db.flush()
    fila = await _fila_json(db, persona.id)
    for claro in (DOC, "1020304", "3001234567", "ana.perez@mail.com", "2000-01-02", "Ana Pérez"):
        assert claro not in fila
    assert fila.count("apx1.") == 5
    assert persona.document is not None and persona.document.is_sealed
    assert persona.document.blob.startswith("apx1.")
    assert persona.document_idx == bus.blind_index("member.document", "1020304")
    assert persona.phone_idx == bus.blind_index("member.phone", "3001234567")
    assert persona.email_idx == bus.blind_index("member.email", "ana.perez@mail.com")


async def test_reveal_devuelve_el_valor_tipado_y_exige_proposito(db: AsyncSession) -> None:
    persona = _persona()
    db.add(persona)
    await db.flush()
    db.expunge(persona)
    cargada = await db.get(CryptoTestPerson, persona.id)
    assert cargada is not None
    assert reveal(cargada, "document", "mask") == DOC
    assert reveal(cargada, "birth_date", "reveal") == date(2000, 1, 2)
    assert reveal(cargada, "emergency_contact", "notify") == CONTACTO
    assert reveal(cargada, "phone", "auth_link") == "+57 300 123 4567"
    with pytest.raises(CryptoError):
        reveal(cargada, "document", "curiosidad")
    with pytest.raises(CryptoError):
        reveal(cargada, "name", "mask")


async def test_cambiar_el_telefono_recifra_y_reindexa_en_el_mismo_flush(db: AsyncSession) -> None:
    persona = _persona()
    db.add(persona)
    await db.flush()
    assert persona.phone is not None
    blob_antes, idx_antes = persona.phone.blob, persona.phone_idx
    persona.phone = Secret.from_plain("3017654321")
    await db.flush()
    assert persona.phone.blob != blob_antes and persona.phone.blob.startswith("apx1.")
    assert persona.phone_idx != idx_antes
    assert persona.phone_idx == bus.blind_index("member.phone", "3017654321")
    assert reveal(persona, "phone", "mask") == "3017654321"


async def test_none_deja_null_en_ambas_columnas(db: AsyncSession) -> None:
    persona = _persona(phone=None)
    db.add(persona)
    await db.flush()
    assert persona.phone is None and persona.phone_idx is None
    persona.document = None
    await db.flush()
    assert persona.document is None and persona.document_idx is None
    fila = await _fila_json(db, persona.id)
    assert '"document":null' in fila and '"document_idx":null' in fila


async def test_cambiar_el_id_falla(db: AsyncSession) -> None:
    persona = _persona()
    db.add(persona)
    await db.flush()
    persona.id = uuid4()
    with pytest.raises(CryptoError) as excinfo:
        await db.flush()
    assert excinfo.value.code == "id_immutable"
    await db.rollback()


async def test_texto_en_claro_falla_por_orm_y_por_core(db: AsyncSession) -> None:
    persona = _persona(document="1020304")  # str, no Secret
    db.add(persona)
    with pytest.raises(CryptoError) as orm:
        await db.flush()
    assert orm.value.code == "plaintext"
    await db.rollback()
    # SQLAlchemy envuelve el error del TypeDecorator en StatementError; el original es el nuestro.
    with pytest.raises(StatementError) as core:
        async with db.begin_nested():
            await db.execute(
                insert(CryptoTestPerson).values(
                    id=uuid4(), name="x", document="1020304", created_by=SYSTEM_USER_ID
                )
            )
    assert isinstance(core.value.orig, CryptoError) and core.value.orig.code == "plaintext"


async def test_un_indice_asignado_a_mano_falla(db: AsyncSession) -> None:
    persona = _persona()
    db.add(persona)
    await db.flush()
    persona.document_idx = "a" * 64
    with pytest.raises(CryptoError) as excinfo:
        await db.flush()
    assert excinfo.value.code == "index_manual"
    await db.rollback()


async def test_un_blob_copiado_a_otro_registro_no_se_abre(db: AsyncSession) -> None:
    a, b = _persona(), _persona(name="Eva")
    db.add_all([a, b])
    await db.flush()
    assert a.document is not None
    await db.execute(
        text(f"UPDATE {SCHEMA}.crypto_test_person SET document = :blob WHERE id = :id"),  # noqa: S608 - SCHEMA es una constante de prueba
        {"blob": a.document.blob, "id": b.id},
    )
    db.expunge(b)
    copiada = await db.get(CryptoTestPerson, b.id)
    assert copiada is not None
    with pytest.raises(CryptoError) as excinfo:
        reveal(copiada, "document", "mask")
    assert excinfo.value.code == "decrypt_failed"


async def test_select_por_indice_ciego(db: AsyncSession) -> None:
    db.add_all([_persona(), _persona(name="Eva", document=Secret.from_plain("99"))])
    await db.flush()
    indice = bus.blind_index("member.document", "1020-304")
    encontrada = await db.scalar(
        select(CryptoTestPerson).where(CryptoTestPerson.document_idx == indice)
    )
    assert encontrada is not None and encontrada.name == "Ana"


# V10 del Sprint 3 (L-B): una fecha corrupta no repite su valor en el error ----------------------


def test_una_fecha_corrupta_da_crypto_error_sin_el_valor() -> None:
    from app.core.crypto.registry import get_spec
    from app.core.crypto.types import _from_bytes

    valor = "1999-13-45-MARCA"
    with pytest.raises(CryptoError) as capturado:
        _from_bytes(valor.encode("ascii"), get_spec("member.birth_date"))
    error = capturado.value
    assert error.code == "blob_invalid"
    assert valor not in str(error) and "MARCA" not in repr(error)
    assert error.__cause__ is None and error.__suppress_context__  # sin la causa con el valor


def test_una_fecha_que_no_es_ascii_da_crypto_error_sin_el_valor() -> None:
    from app.core.crypto.registry import get_spec
    from app.core.crypto.types import _from_bytes

    with pytest.raises(CryptoError) as capturado:
        _from_bytes("2000-01-0ñ".encode(), get_spec("member.birth_date"))
    assert capturado.value.code == "blob_invalid"
    assert capturado.value.__cause__ is None and capturado.value.__suppress_context__
