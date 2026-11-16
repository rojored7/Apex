"""`members.service.consent_missing_for` (S9-A1, S9-D29, H-1). Rojo A1.

De los ids pedidos, devuelve los socios SIN autorización de datos vigente, con la misma
`CONSENT_MISSING_CONDITION` de `count_without_consent` (`data_consent_at IS NULL`):
- con autorización: no está; sin ella: está;
- un id inexistente no aparece (no se inventa);
- un socio dado de baja sin autorización SÍ aparece (la función no mira `deleted_at`: quien escribe
  decide antes si el socio existe, y el 404 de la baja va primero);
- ids repetidos o una lista vacía: sin error y sin consulta si no hay nada que pedir;
- una sola consulta sobre `members.members` y ningún descifrado.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members import service
from tests.conftest import ContadorDeConsultas
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("bus_listo")


async def test_con_ids_vacios_devuelve_un_conjunto_vacio_sin_consultar(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo() as contador:
        resultado = await service.consent_missing_for(session, [])
    assert resultado == set() and type(resultado) is set
    assert contador.sentencias == []


async def test_solo_devuelve_a_los_socios_sin_autorizacion(session: AsyncSession) -> None:
    con = await socio(session, nombre="Ana", consentido=True)
    sin = await socio(session, nombre="Bea", consentido=False)
    otra_sin = await socio(session, nombre="Caro", consentido=False)

    resultado = await service.consent_missing_for(session, [con.id, sin.id, otra_sin.id])

    assert resultado == {sin.id, otra_sin.id}


async def test_un_id_inexistente_no_aparece(session: AsyncSession) -> None:
    sin = await socio(session, nombre="Bea", consentido=False)

    resultado = await service.consent_missing_for(session, [sin.id, uuid4()])

    assert resultado == {sin.id}


async def test_solo_mira_los_ids_pedidos(session: AsyncSession) -> None:
    pedido = await socio(session, nombre="Ana", consentido=True)
    await socio(session, nombre="Bea", consentido=False)

    assert await service.consent_missing_for(session, [pedido.id]) == set()


async def test_un_socio_dado_de_baja_sin_autorizacion_aparece(session: AsyncSession) -> None:
    baja = await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")

    assert await service.consent_missing_for(session, [baja.id]) == {baja.id}


async def test_acepta_ids_repetidos_y_cualquier_iterable(session: AsyncSession) -> None:
    sin = await socio(session, nombre="Bea", consentido=False)

    assert await service.consent_missing_for(session, [sin.id, sin.id]) == {sin.id}
    assert await service.consent_missing_for(session, (i for i in [sin.id])) == {sin.id}


async def test_es_una_sola_consulta_sobre_members_y_no_descifra(
    session: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    uno = await socio(session, nombre="Ana", consentido=False)
    dos = await socio(session, nombre="Bea", consentido=True)
    tres = await socio(session, nombre="Caro", consentido=False)

    with contador_de_consultas.midiendo() as contador:
        resultado = await service.consent_missing_for(session, [uno.id, dos.id, tres.id])

    assert resultado == {uno.id, tres.id}
    assert contador.de("members.members") == 1, contador.sentencias
    assert len(contador.sentencias) == 1, contador.sentencias
    assert not any("crypto_ops" in sentencia for sentencia in contador.sentencias)


async def test_coincide_con_count_without_consent(session: AsyncSession) -> None:
    """La misma condición que el KPI: los vivos sin autorización son los que cuenta el KPI."""
    creados = [
        await socio(session, nombre="Ana", consentido=True),
        await socio(session, nombre="Bea", consentido=False),
        await socio(session, nombre="Caro", consentido=False),
    ]

    faltan = await service.consent_missing_for(session, [m.id for m in creados])

    assert len(faltan) == await service.count_without_consent(session) == 2
