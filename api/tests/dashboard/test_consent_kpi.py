"""`members_without_consent` del tablero = total de `GET /members?consent=missing` (S6-C5, US-151).

Socios mezclados: con autorización, sin ella y uno de baja sin ella (no cuenta en ninguno de los
dos lados). Los dos números salen de la misma condición (`CONSENT_MISSING_CONDITION`).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from tests.conftest import Cabeceras, UsuarioPrueba
from tests.dashboard._apoyo import DASHBOARD
from tests.members._apoyo import MEMBERS
from tests.notifications._apoyo_avisos import ANTES, socio


@pytest.fixture
async def mezcla(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> None:
    await socio(session, nombre="Ana", consentido=True)
    await socio(session, nombre="Bea", consentido=True)
    await socio(session, nombre="Caro", consentido=False)
    await socio(session, nombre="Dina", consentido=False)
    await socio(session, nombre="Gema", consentido=False)
    await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")


@pytest.mark.usefixtures("mezcla")
async def test_el_kpi_es_igual_al_total_del_filtro(
    app_http: AsyncClient, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    tablero = await app_http.get(DASHBOARD, headers=cabeceras(ana))
    lista = await app_http.get(MEMBERS, params={"consent": "missing"}, headers=cabeceras(ana))
    assert tablero.status_code == 200, tablero.text
    assert lista.status_code == 200, lista.text
    assert tablero.json()["members_without_consent"] == lista.json()["total"] == 3
    assert len(lista.json()["items"]) == 3


async def test_con_todos_autorizados_ambos_son_cero(
    app_http: AsyncClient,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await socio(session, nombre="Ana", consentido=True)
    await socio(session, nombre="Eva", consentido=False, deleted_at=ANTES, status="inactive")
    tablero = await app_http.get(DASHBOARD, headers=cabeceras(ana))
    lista = await app_http.get(MEMBERS, params={"consent": "missing"}, headers=cabeceras(ana))
    assert tablero.json()["members_without_consent"] == 0
    assert lista.json()["total"] == 0 and lista.json()["items"] == []
