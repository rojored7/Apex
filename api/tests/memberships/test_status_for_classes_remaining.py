"""`status_for` suma `classes_remaining` de la membresía que decide (S7-R2, US-163; S7-D15)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memberships import service
from tests.factories.members import make_members
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def test_tiquetera_trae_las_clases_que_quedan_y_mensual_none(session: AsyncSession) -> None:
    mensual = await make_plan(session, name="Mensual")
    tiquetera = await make_plan(
        session, name="Tiquetera", kind="classes", class_count=12, duration_days=90
    )
    con_clases, sin_clases = await make_members(session, 2)
    await make_membership(session, con_clases, tiquetera, status="active", classes_remaining=5)
    await make_membership(session, sin_clases, mensual, status="active")
    estados = await service.status_for(session, [con_clases.id, sin_clases.id])
    assert estados[con_clases.id].classes_remaining == 5
    assert estados[sin_clases.id].classes_remaining is None
