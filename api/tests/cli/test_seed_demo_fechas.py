"""`seed --demo` deja las fechas que declara `demo_dataset` (S4B-B1, US-111; S4B-D32).

El catálogo promete `expected_end_date` por venta (con la congelación ya sumada); si la base
guardara otro fin, el tablero y los estados de la demostración dejarían de cuadrar con el plan.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.memberships.models import Membership
from app.modules.plans.models import Plan
from tests.cli import _apoyo_demo as demo
from tests.cli.test_seed_demo import _sembrar

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


async def test_los_fines_guardados_son_los_del_catalogo(
    limpiar_demo: async_sessionmaker[AsyncSession],
    settings_prueba: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0  # type: ignore[arg-type]

    async with limpiar_demo() as sesion:
        filas = await sesion.execute(
            select(Plan.name, Membership.start_date, Membership.end_date).join(
                Plan, Plan.id == Membership.plan_id
            )
        )
        guardadas = {(nombre, inicio, fin) for nombre, inicio, fin in filas}
    esperadas = {
        (s.sale.plan_name, s.sale.start_date, s.sale.expected_end_date)
        for s in demo.catalogo().members
    }
    assert esperadas <= guardadas, sorted(esperadas - guardadas)
