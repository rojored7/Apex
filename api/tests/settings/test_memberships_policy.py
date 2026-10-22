"""`memberships_policy()` para Memberships (US-058 T4; S2-D45): defaults, guardado, inmutable."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.schemas import MembershipsPolicy
from app.modules.settings.service import memberships_policy, update_section
from tests.settings._apoyo import ADMIN_ID, MEMBERSHIPS_DEFAULTS, MEMBERSHIPS_OK


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


async def test_sin_fila_devuelve_los_defaults_7_30_2_7(db: AsyncSession) -> None:
    politica = await memberships_policy(db)
    assert politica == MembershipsPolicy(7, 30, 2, 7)
    assert dataclasses.asdict(politica) == MEMBERSHIPS_DEFAULTS


async def test_despues_de_guardar_devuelve_lo_guardado(db: AsyncSession) -> None:
    await update_section(db, "memberships", MEMBERSHIPS_OK, 0, ADMIN_ID)
    politica = await memberships_policy(db)
    assert politica.expiring_days == 5
    assert dataclasses.asdict(politica) == MEMBERSHIPS_OK


async def test_la_politica_es_inmutable(db: AsyncSession) -> None:
    politica = await memberships_policy(db)
    assert isinstance(politica, MembershipsPolicy)
    with pytest.raises(dataclasses.FrozenInstanceError):
        politica.expiring_days = 1  # type: ignore[misc]
