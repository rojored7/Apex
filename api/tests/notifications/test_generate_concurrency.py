"""Dos corridas de `generate_today` a la vez (S5-B7 revisiones; S5-D223). # Rojo B7

`generate_today` toma `pg_advisory_xact_lock(hashtext('apex:generate:notifications'))` al inicio de
cada lote: dos corridas (api y worker, o dos CLI) se serializan, el total es el de una sola y
ningún aviso se duplica ni se pierde. Usa `dos_sesiones` (commit real) y las llaves confirmadas de
`bus_confirmado`; por eso vive aparte de `test_generate.py` (cuya `listo` usa la sesión con
savepoint).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.notifications import service
from tests.factories.members import make_members
from tests.factories.memberships import make_memberships
from tests.factories.plans import make_plan
from tests.notifications._apoyo_avisos import (
    ANTES,
    HOY,
    T_AVISOS,
    ajustar_canales,
    regla_aislada,
)


async def test_dos_corridas_concurrentes_no_duplican_ni_pierden_avisos(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    await ajustar_canales(primera, whatsapp=True)  # V11c: sin fila el canal está apagado
    await regla_aislada(primera, "membership_expiring", -3)
    plan = await make_plan(primera)
    socios = await make_members(primera, 6, data_consent_at=ANTES)
    await make_memberships(
        primera,
        6,
        plan,
        members=socios,
        status="active",
        start=HOY - timedelta(days=26),
        end=HOY + timedelta(days=3),
    )

    with actor_scope(SYSTEM_USER_ID):
        resultados = await asyncio.gather(
            service.generate_today(primera, HOY), service.generate_today(segunda, HOY)
        )

    assert sorted(r.generados for r in resultados) == [0, 6]
    total = await primera.scalar(text(f"SELECT count(*) FROM {T_AVISOS}"))  # noqa: S608
    assert total == 6


async def test_la_corrida_espera_el_candado_de_generacion(
    bus_confirmado: Keyring,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
) -> None:
    """Si otra transacción tiene el candado, la corrida espera y con `lock_timeout` falla sin
    escribir nada (el candado es lo primero del lote)."""
    import pytest
    from sqlalchemy.exc import DBAPIError

    primera, segunda = dos_sesiones
    await regla_aislada(primera, "membership_expiring", -3)
    plan = await make_plan(primera)
    socios = await make_members(primera, 2, data_consent_at=ANTES)
    await make_memberships(
        primera,
        2,
        plan,
        members=socios,
        status="active",
        start=HOY - timedelta(days=26),
        end=HOY + timedelta(days=3),
    )
    await primera.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "apex:generate:notifications"}
    )
    try:
        with actor_scope(SYSTEM_USER_ID), pytest.raises(DBAPIError):
            await segunda.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await service.generate_today(segunda, HOY)
        await segunda.rollback()
    finally:
        await primera.rollback()
    total = await primera.scalar(text(f"SELECT count(*) FROM {T_AVISOS}"))  # noqa: S608
    assert total == 0
