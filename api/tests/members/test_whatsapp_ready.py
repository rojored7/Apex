"""`members.service.whatsapp_ready` (S9-X1, S9-D22, S9-D36 L-5). Rojo X1.

De los ids pedidos devuelve `{id: bool}`; verdadero solo si el socio existe, no está dado de baja
(`deleted_at IS NULL`), tiene autorización de datos (`NOT CONSENT_MISSING_CONDITION`) y tiene
teléfono (`phone IS NOT NULL`):
- con teléfono, autorización y vivo: True; sin teléfono, sin autorización o dado de baja: False;
- cada id pedido tiene entrada (un id inexistente es False);
- una sola consulta sobre `members.members` por lote (ninguna con la lista vacía);
- no descifra: cero filas nuevas en `crypto.crypto_ops` y en `audit.audit_log`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members import service
from tests.conftest import ContadorDeConsultas
from tests.notifications._apoyo_avisos import ANTES, TELEFONO, socio

pytestmark = pytest.mark.usefixtures("bus_listo")


async def test_con_telefono_autorizacion_y_vivo_es_verdadero(session: AsyncSession) -> None:
    listo = await socio(session, phone=TELEFONO)

    assert await service.whatsapp_ready(session, [listo.id]) == {listo.id: True}


async def test_sin_telefono_es_falso(session: AsyncSession) -> None:
    sin = await socio(session, phone=None)

    assert await service.whatsapp_ready(session, [sin.id]) == {sin.id: False}


async def test_sin_autorizacion_de_datos_es_falso(session: AsyncSession) -> None:
    sin = await socio(session, phone=TELEFONO, consentido=False)

    assert await service.whatsapp_ready(session, [sin.id]) == {sin.id: False}


async def test_dado_de_baja_es_falso(session: AsyncSession) -> None:
    baja = await socio(session, phone=TELEFONO, deleted_at=ANTES, status="inactive")

    assert await service.whatsapp_ready(session, [baja.id]) == {baja.id: False}


async def test_un_lote_mixto_responde_cada_id_y_uno_inexistente_es_falso(
    session: AsyncSession,
) -> None:
    bueno = await socio(session, nombre="Ana", phone=TELEFONO)
    sin_tel = await socio(session, nombre="Bea", phone=None)
    sin_aut = await socio(session, nombre="Caro", phone=TELEFONO, consentido=False)
    baja = await socio(session, nombre="Eva", phone=TELEFONO, deleted_at=ANTES, status="inactive")
    fantasma = uuid4()

    resultado = await service.whatsapp_ready(
        session, [bueno.id, sin_tel.id, sin_aut.id, baja.id, fantasma]
    )

    assert resultado == {
        bueno.id: True,
        sin_tel.id: False,
        sin_aut.id: False,
        baja.id: False,
        fantasma: False,
    }


async def test_con_ids_vacios_devuelve_un_dict_vacio_sin_consultar(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo() as contador:
        resultado = await service.whatsapp_ready(session, [])

    assert resultado == {}
    assert contador.sentencias == []


async def test_es_una_sola_consulta_sobre_members_por_lote(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    uno = await socio(session, nombre="Ana", phone=TELEFONO)
    dos = await socio(session, nombre="Bea", phone=None)
    tres = await socio(session, nombre="Caro", phone=TELEFONO)

    with contador_de_consultas.midiendo() as contador:
        resultado = await service.whatsapp_ready(session, [uno.id, dos.id, tres.id])

    assert resultado == {uno.id: True, dos.id: False, tres.id: True}
    assert contador.de("members.members") == 1, contador.sentencias
    assert len(contador.sentencias) == 1, contador.sentencias


async def test_no_descifra_ni_deja_filas_en_crypto_ops_ni_en_auditoria(
    session: AsyncSession,
) -> None:
    uno = await socio(session, nombre="Ana", phone=TELEFONO)
    dos = await socio(session, nombre="Bea", phone=None)
    ops_antes = (await session.execute(text("SELECT count(*) FROM crypto.crypto_ops"))).scalar_one()
    audit_antes = (await session.execute(text("SELECT count(*) FROM audit.audit_log"))).scalar_one()

    await service.whatsapp_ready(session, [uno.id, dos.id])

    ops = (await session.execute(text("SELECT count(*) FROM crypto.crypto_ops"))).scalar_one()
    audit = (await session.execute(text("SELECT count(*) FROM audit.audit_log"))).scalar_one()
    assert (ops, audit) == (ops_antes, audit_antes)
