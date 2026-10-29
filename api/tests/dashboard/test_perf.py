"""Rendimiento del tablero (S4A-B8, US-108; S4A-D27, S4A-D68). Marcada `perf`: no es gate; se corre
aparte con `uv run pytest -m perf tests/dashboard/test_perf.py -q`.

1.000 socios con una membresía cada uno y 12 meses de pagos (uno por socio y mes, 12.000 pagos,
por Core en lotes), la cadena con las filas de esos inserts del sistema y 200 escrituras de ana:
`dashboard.service.summary` con la caché del resumen apagada (`sin_cache_de_resumen`, TTL 0)
responde en menos de 300 ms (mediana de 5, tras un calentamiento).
"""

from __future__ import annotations

import statistics
import time
from datetime import timedelta
from typing import Any, Final
from uuid import uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.modules.memberships.models import Membership
from app.modules.payments.models import Payment
from tests.conftest import UsuarioPrueba
from tests.dashboard.conftest import dashboard_service
from tests.factories.audit_chain import make_audit_chain
from tests.factories.members import make_members
from tests.factories.plans import make_plan

pytestmark = pytest.mark.perf

SOCIOS: Final = 1_000
MESES: Final = 12
TOPE_MS: Final = 300
LOTE: Final = 2_000


@pytest.fixture
async def mil_socios(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    audit_chain_factory: Any,
    ana: UsuarioPrueba,
) -> None:
    plan = await make_plan(session, name="Plan Perf Tablero")
    socios = await make_members(session, SOCIOS)
    hoy = reloj.today_bogota()
    membresias = [
        {
            "id": uuid4(),
            "member_id": socio.id,
            "plan_id": plan.id,
            "agreed_price_cop": 120_000,
            "start_date": hoy - timedelta(days=indice % 40),
            "end_date": hoy + timedelta(days=30 - indice % 40),
            "classes_total": None,
            "classes_remaining": None,
            "status": "active",
            "created_by": SYSTEM_USER_ID,
        }
        for indice, socio in enumerate(socios)
    ]
    await session.execute(insert(Membership), membresias)
    ahora = reloj.now_utc()
    pagos: list[dict[str, Any]] = []
    for mes in range(MESES):
        for membresia in membresias:
            pagos.append(
                {
                    "membership_id": membresia["id"],
                    "member_id": membresia["member_id"],
                    "amount_cop": 120_000,
                    "method": "cash",
                    "paid_at": ahora - timedelta(days=30 * mes, minutes=1),
                    "registered_by": SYSTEM_USER_ID,
                    "voided": False,
                    "created_by": SYSTEM_USER_ID,
                }
            )
    for inicio in range(0, len(pagos), LOTE):
        await session.execute(insert(Payment), pagos[inicio : inicio + LOTE])
    await session.commit()
    await make_audit_chain(session, 200, table_name="payments.payments", user_id=ana.id)
    await session.execute(text("ANALYZE"))


async def test_el_resumen_del_tablero_baja_de_300_ms(
    session: AsyncSession, mil_socios: None
) -> None:
    await dashboard_service.summary(session, with_finances=True)  # calentamiento
    tiempos: list[float] = []
    for _ in range(5):
        inicio = time.perf_counter()
        tablero = await dashboard_service.summary(session, with_finances=True)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    vivos = tablero.members_active + tablero.members_expiring + tablero.members_expired
    assert vivos == SOCIOS
    assert tablero.income_month_cop > 0
    assert len(tablero.last_movements) == 10
    assert statistics.median(tiempos) < TOPE_MS, [round(t, 1) for t in tiempos]
