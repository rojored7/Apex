"""`members.service.count_without_consent` (S5-B10, US-132; S5-D80, Q6). # Rojo B10

Cuenta los socios NO dados de baja (`deleted_at IS NULL`) con `data_consent_at IS NULL`:
- sin socios, 0;
- con y sin consentimiento mezclados: solo cuentan los vivos sin él;
- un socio dado de baja sin consentimiento NO cuenta; uno dado de baja con consentimiento tampoco;
- reactivar (volver `deleted_at` a `NULL`) lo hace contar de nuevo;
- es un entero y una sola consulta sobre `members.members`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members import service
from app.modules.members.models import Member
from tests.conftest import ContadorDeConsultas
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("bus_listo")


async def test_sin_socios_cuenta_cero(session: AsyncSession) -> None:
    resultado = await service.count_without_consent(session)
    assert resultado == 0 and type(resultado) is int


async def test_cuenta_solo_los_vivos_sin_consentimiento(session: AsyncSession) -> None:
    await socio(session, nombre="Ana", consentido=True)
    await socio(session, nombre="Bea", consentido=True)
    await socio(session, nombre="Caro", consentido=False)
    await socio(session, nombre="Dina", consentido=False)
    await socio(session, nombre="Gema", consentido=False)

    assert await service.count_without_consent(session) == 3


async def test_un_socio_dado_de_baja_sin_consentimiento_no_cuenta(session: AsyncSession) -> None:
    await socio(session, nombre="Caro", consentido=False)
    await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")
    await socio(session, nombre="Fran", consentido=True, deleted_at=ANTES, status="inactive")

    assert await service.count_without_consent(session) == 1


async def test_reactivar_a_un_socio_sin_consentimiento_vuelve_a_contarlo(
    session: AsyncSession,
) -> None:
    eva = await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")
    assert await service.count_without_consent(session) == 0

    await session.execute(
        update(Member).where(Member.id == eva.id).values(deleted_at=None, status="active")
    )

    assert await service.count_without_consent(session) == 1


async def test_es_una_sola_consulta_sobre_members(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    await socio(session, nombre="Caro", consentido=False)
    with contador_de_consultas.midiendo() as contador:
        resultado = await service.count_without_consent(session)
    assert resultado == 1
    assert contador.de("members.members") == 1, contador.sentencias
    assert len(contador.sentencias) == 1, contador.sentencias
