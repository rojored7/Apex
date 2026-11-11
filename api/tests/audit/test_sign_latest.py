"""`sign_latest`, `check_unsigned_segment` y `latest_signature` (S6-A1, US-140; S6-D3, S6-D34, H-1).

Rojo: `core/audit_sign.py` es un stub que lanza `NotImplementedError`. La firma guarda el hash de
la fila `through_seq` (ADR-006); antes de firmar se recorre el tramo sin firmar recalculando la
cadena con `core.audit.chain_hash` (solo lectura) y se compara con el ancla: la última firma. Si
no cuadra no se firma. Cada prueba usa `firmador`: cadena vacía, bus listo con la fila `sign`
`local` y actor del sistema, dentro del savepoint de la prueba.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit_sign
from app.core.audit_sign import AuditSignature
from app.core.context import SYSTEM_USER_ID
from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from app.core.crypto.models import CryptoOp
from tests.audit.conftest import CadenaDePrueba
from tests.factories.signatures import (
    alterar_fila,
    borrar_firma,
    cadena_con_firmas,
    firmar_hasta,
    firmas,
    payload_de,
)

pytestmark = pytest.mark.usefixtures("firmador")


async def _filas(session: AsyncSession) -> list[AuditSignature]:
    return list((await session.scalars(select(AuditSignature).order_by("through_seq"))).all())


# Firmar -----------------------------------------------------------------------------------------


async def test_firma_la_ultima_fila_con_el_payload_de_adr_006(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba, firmador: Keyring
) -> None:
    ultimo = await audit_chain_factory.make(5)

    salida = await audit_sign.sign_latest(session)

    assert (salida.kind, salida.through_seq) == ("signed", ultimo)
    assert salida.signature_id is not None
    (fila,) = await _filas(session)
    llave = firmador.active_for("sign", "audit.signature")
    hash_final = await audit_chain_factory.hash_of(5)
    assert fila.id == salida.signature_id
    assert (fila.through_seq, fila.chain_hash) == (5, hash_final)
    assert fila.key_id == llave.key_id and fila.algorithm == "Ed25519"
    assert fila.payload_version == 1 and fila.created_by == SYSTEM_USER_ID
    assert fila.signed_at is not None
    assert fila.signature.startswith("apx1.") and fila.signature.split(".")[2] == "Ed25519"
    assert hash_final is not None
    assert await bus.verify("audit.signature", payload_de(5, hash_final), fila.signature) is True


async def test_deja_crypto_ops_sign_con_la_clase_y_la_llave(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba, firmador: Keyring
) -> None:
    await audit_chain_factory.make(3)

    await audit_sign.sign_latest(session)
    await session.commit()

    llave = firmador.active_for("sign", "audit.signature")
    ops = list(
        (
            await session.scalars(
                select(CryptoOp).where(
                    CryptoOp.verb == "sign", CryptoOp.data_class == "audit.signature"
                )
            )
        ).all()
    )
    assert len(ops) == 1
    assert ops[0].key_id == llave.key_id and ops[0].result == "ok"


async def test_by_queda_en_created_by(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(2)
    quien = uuid4()

    await audit_sign.sign_latest(session, by=quien)

    (fila,) = await _filas(session)
    assert fila.created_by == quien


async def test_sin_filas_en_la_cadena_no_hay_nada_nuevo(session: AsyncSession) -> None:
    salida = await audit_sign.sign_latest(session)

    assert (salida.kind, salida.through_seq, salida.signature_id) == ("nothing_new", 0, None)
    assert await _filas(session) == []


async def test_no_firma_dos_veces_el_mismo_through_seq(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(4)
    primera = await audit_sign.sign_latest(session)

    segunda = await audit_sign.sign_latest(session)

    assert primera.kind == "signed"
    assert (segunda.kind, segunda.through_seq, segunda.signature_id) == ("nothing_new", 4, None)
    assert len(await _filas(session)) == 1


async def test_con_filas_nuevas_firma_otra_vez_y_la_ultima_es_latest(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    assert await audit_sign.latest_signature(session) is None
    salidas = await cadena_con_firmas(session, [4, 3])

    assert [(s.kind, s.through_seq) for s in salidas] == [("signed", 4), ("signed", 7)]
    ultima = await audit_sign.latest_signature(session)
    assert ultima is not None and ultima.through_seq == 7
    assert [f.through_seq for f in await _filas(session)] == [4, 7]


async def test_el_primer_firmado_de_una_base_sin_firmas_recorre_desde_seq_1(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """Sin ancla previa el tramo empieza en `seq = 1` con `prev_hash = ZERO_HASH`: una fila 1
    alterada rompe la firma aunque sea la primera de la historia."""
    await audit_chain_factory.make(6)
    await alterar_fila(session, 1)

    salida = await audit_sign.sign_latest(session)

    assert (salida.kind, salida.through_seq) == ("chain_broken", 1)
    assert await _filas(session) == []


# H-1: verificación incremental antes de firmar ---------------------------------------------------


async def test_una_fila_alterada_entre_dos_firmas_impide_firmar(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(5)
    await audit_sign.sign_latest(session)
    await audit_chain_factory.make(3)  # seq 6..8
    await alterar_fila(session, 7)

    salida = await audit_sign.sign_latest(session)

    assert salida.kind == "chain_broken" and salida.signature_id is None
    assert salida.through_seq == 7  # el seq roto, el que viaja en la alerta `audit_chain_broken`
    assert [f.through_seq for f in await _filas(session)] == [5]  # ninguna fila nueva


async def test_check_unsigned_segment_sana_y_rota_con_broken_at_seq(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(8)
    ancla = await audit_chain_factory.hash_of(5)
    assert ancla is not None

    sana = await audit_sign.check_unsigned_segment(session, from_seq=6, to_seq=8, anchor_hash=ancla)
    assert (sana.ok, sana.from_seq, sana.to_seq, sana.broken_at_seq) == (True, 6, 8, None)

    await alterar_fila(session, 7)
    rota = await audit_sign.check_unsigned_segment(session, from_seq=6, to_seq=8, anchor_hash=ancla)
    assert (rota.ok, rota.broken_at_seq) == (False, 7)
    # Un tramo que no llega a la fila alterada sigue sano: se recalcula solo lo pedido.
    corto = await audit_sign.check_unsigned_segment(
        session, from_seq=6, to_seq=6, anchor_hash=ancla
    )
    assert corto.ok is True


async def test_check_unsigned_segment_recalcula_con_el_serializador_canonico(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """Una fila reescrita Y re-encadenada (cola consistente) pasa el recorrido interno del tramo
    pero no el ancla: el `prev_hash` de la primera fila ya no es el hash firmado."""
    await audit_chain_factory.make(8)
    ancla = await audit_chain_factory.hash_of(5)
    assert ancla is not None
    await alterar_fila(session, 4, rehash=True)  # seq 4..8 recalculadas, coherentes entre sí

    revision = await audit_sign.check_unsigned_segment(
        session, from_seq=6, to_seq=8, anchor_hash=ancla
    )

    assert (revision.ok, revision.broken_at_seq) == (False, 6)


async def test_cola_reescrita_antes_del_ancla_no_firma(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(5)
    await audit_sign.sign_latest(session)  # ancla en 5
    await audit_chain_factory.make(3)
    await alterar_fila(session, 3, rehash=True)  # la historia firmada cambió de hash

    salida = await audit_sign.sign_latest(session)

    assert salida.kind == "chain_broken" and salida.signature_id is None
    assert [f.through_seq for f in await _filas(session)] == [5]


async def test_ancla_que_no_coincide_tras_borrar_la_ultima_firma_y_reescribir(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """Se firma en 5 y en 8; se borra la firma de 8 y se reescribe desde la fila 4: la ancla
    vigente (5) ya no coincide con el hash de la fila 5, así que no se firma otra vez."""
    await cadena_con_firmas(session, [5, 3])
    await borrar_firma(session, 8)
    await alterar_fila(session, 4, rehash=True)
    await audit_chain_factory.make(2)

    salida = await audit_sign.sign_latest(session)

    assert salida.kind == "chain_broken" and salida.signature_id is None
    assert [f.through_seq for f in await _filas(session)] == [5]


async def test_firmar_hasta_de_la_fabrica_usa_el_mismo_payload_que_el_oraculo(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    await audit_chain_factory.make(3)
    await firmar_hasta(session, 3)

    (fila,) = await firmas(session)
    assert fila["hash"] == await audit_chain_factory.hash_of(3)
    siguiente = await audit_sign.sign_latest(session)
    assert (siguiente.kind, siguiente.through_seq) == ("nothing_new", 3)


# Ancla explícita (M4) y huecos de `seq` (LOW 6) --------------------------------------------------


async def test_la_fila_firmada_alterada_rompe_el_ancla_en_su_seq(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """`alterar_fila` justo en la fila firmada: el hash guardado ya no es el firmado."""
    await audit_chain_factory.make(5)
    await audit_sign.sign_latest(session)
    await audit_chain_factory.make(2)
    await alterar_fila(session, 5)

    salida = await audit_sign.sign_latest(session)

    assert (salida.kind, salida.through_seq, salida.signature_id) == ("chain_broken", 5, None)
    assert [f.through_seq for f in await _filas(session)] == [5]


async def test_un_hueco_de_seq_es_ruptura_igual_que_en_audit_verify(
    session: AsyncSession, audit_chain_factory: CadenaDePrueba
) -> None:
    """`verify_chain` exige `seq` consecutivos y `audit_verify._scan_chain` marca la ruptura en la
    primera fila presente tras el hueco: el tramo sin firmar aplica el mismo criterio."""
    from app.core import audit_verify
    from tests.factories import audit_chain

    await audit_chain_factory.make(8)
    await audit_chain.drop_rows(session, [6])

    salida = await audit_sign.sign_latest(session)
    verificacion = await audit_verify.run_verification(session, source="cli", by=SYSTEM_USER_ID)

    assert (salida.kind, salida.signature_id) == ("chain_broken", None)
    assert verificacion.ok is False
    assert salida.through_seq == verificacion.broken_at_seq == 7
    assert await _filas(session) == []
