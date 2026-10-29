"""`dashboard.service.summary` (S4A-B8, US-108; S4A-D27, S4A-D29).

Con fábricas (todo bajo `SYSTEM_USER_ID`, así que `last_movements` sale vacío) y el reloj de la
app en 2026-10-20 (Bogotá):
- los cinco conteos son idénticos a `memberships.service.summary(session, today=hoy)` y
  `income_month_cop` a `payments.service.summary(session, "2026-10").total_cop` (el tablero no
  recalcula estados ni suma pagos);
- `today` es el día de Bogotá del reloj de la app, e `income_month` su mes;
- borde de mes: con el reloj en 2026-11-01T01:00Z (20:00 del 31 de octubre en Bogotá) el mes es
  2026-10 y un pago con `paid_at` 2026-11-01T03:00Z (22:00 del 31 en Bogotá) cuenta en octubre;
- los cinco campos futuros están presentes y en `null`.
Valores a mano de `datos`: pagos vigentes de octubre 120.000 + 90.000 + 45.000 = 255.000 (el
anulado de 70.000 y el de septiembre de 300.000 no cuentan).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Final

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.crypto.keyring import Keyring
from app.modules.dashboard.schemas import DashboardOut
from tests.conftest import ContadorDeConsultas
from tests.dashboard._apoyo import CAMPOS_DASHBOARD, FUTUROS
from tests.dashboard.conftest import dashboard_service, memberships_service, payments_service
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan

EN_OCTUBRE: Final = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
HOY: Final = date(2026, 10, 20)
BORDE: Final = datetime(2026, 11, 1, 1, 0, tzinfo=UTC)
PAGO_DEL_BORDE: Final = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
INGRESOS_DE_OCTUBRE: Final = 255_000


@pytest.fixture
def reloj_tablero() -> Iterator[FrozenClock]:
    reloj = FrozenClock(EN_OCTUBRE)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


async def _socio(session: AsyncSession, n: int) -> object:
    return await make_member(
        session, first_name=f"Socio {n}", document=f"91000000{n:02d}", phone=None, email=None
    )


@pytest.fixture
async def datos(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj_tablero: FrozenClock,
    audit_chain_factory: object,
) -> None:
    """Membresías en varios estados y pagos de octubre, septiembre y uno anulado (cadena de
    auditoría vacía al empezar: solo quedan las filas del sistema que escriben las fábricas)."""
    plan = await make_plan(session, name="Plan Mensual Tablero")
    casos = [
        ("active", HOY - timedelta(days=5), HOY + timedelta(days=25)),
        ("active", HOY - timedelta(days=20), HOY + timedelta(days=2)),
        ("active", HOY - timedelta(days=40), HOY - timedelta(days=10)),
        ("pending_payment", HOY, None),
        ("pending_payment", HOY - timedelta(days=1), None),
        ("cancelled", HOY - timedelta(days=3), None),
    ]
    membresias = []
    for n, (estado, inicio, fin) in enumerate(casos):
        socio = await _socio(session, n)
        membresias.append(
            await make_membership(session, socio, plan, status=estado, start=inicio, end=fin)  # type: ignore[arg-type]
        )
    octubre = datetime(2026, 10, 5, 15, 0, tzinfo=UTC)
    await make_payment(session, membresias[0], amount=120_000, paid_at=octubre)
    await make_payment(session, membresias[1], amount=90_000, paid_at=octubre + timedelta(days=1))
    await make_payment(session, membresias[2], amount=45_000, paid_at=octubre + timedelta(days=2))
    await make_payment(session, membresias[0], amount=70_000, paid_at=octubre, voided=True)
    await make_payment(
        session, membresias[2], amount=300_000, paid_at=datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
    )


async def test_los_conteos_son_los_del_resumen_de_membresias(
    session: AsyncSession, datos: None
) -> None:
    tablero = await dashboard_service.summary(session, with_finances=True)
    resumen = await memberships_service.summary(session, today=HOY)
    assert (
        tablero.members_active,
        tablero.members_expiring,
        tablero.members_expired,
        tablero.members_frozen,
        tablero.members_pending_payment,
    ) == (
        resumen.active,
        resumen.expiring,
        resumen.expired,
        resumen.frozen,
        resumen.pending_payment,
    )
    assert resumen.pending_payment == 2
    assert resumen.active + resumen.expiring + resumen.expired >= 3


async def test_los_ingresos_son_los_del_resumen_de_pagos_del_mes(
    session: AsyncSession, datos: None
) -> None:
    tablero = await dashboard_service.summary(session, with_finances=True)
    pagos = await payments_service.summary(session, "2026-10")
    assert tablero.income_month == "2026-10"
    assert tablero.income_month_cop == pagos.total_cop == INGRESOS_DE_OCTUBRE


async def test_today_es_el_dia_de_bogota_del_reloj(session: AsyncSession, datos: None) -> None:
    tablero = await dashboard_service.summary(session, with_finances=True)
    assert tablero.today == HOY


async def test_borde_de_mes_cuenta_el_pago_de_la_noche_del_31_en_octubre(
    session: AsyncSession, datos: None, reloj_tablero: FrozenClock
) -> None:
    membresia = await make_membership(
        session,
        await _socio(session, 50),
        await make_plan(session, name="Plan Borde"),
        status="active",  # type: ignore[arg-type]
    )
    await make_payment(session, membresia, amount=10_000, paid_at=PAGO_DEL_BORDE)
    reloj_tablero.advance(days=11, hours=10)
    assert reloj_tablero.now_utc() == BORDE

    tablero = await dashboard_service.summary(session, with_finances=True)

    assert tablero.today == date(2026, 10, 31)
    assert tablero.income_month == "2026-10"
    assert tablero.income_month_cop == INGRESOS_DE_OCTUBRE + 10_000
    noviembre = await payments_service.summary(session, "2026-11")
    assert noviembre.total_cop == 0


async def test_los_cinco_futuros_estan_presentes_y_en_null(
    session: AsyncSession, datos: None
) -> None:
    tablero = await dashboard_service.summary(session, with_finances=True)
    assert isinstance(tablero, DashboardOut)
    cuerpo = tablero.model_dump(mode="json")
    assert set(cuerpo) == CAMPOS_DASHBOARD
    assert {campo: cuerpo[campo] for campo in FUTUROS} == dict.fromkeys(FUTUROS)


async def test_el_trabajo_del_sistema_no_sale_en_los_movimientos(
    session: AsyncSession, datos: None
) -> None:
    """Las fábricas escriben como `SYSTEM_USER_ID`: el tablero no muestra nada de eso."""
    tablero = await dashboard_service.summary(session, with_finances=True)
    assert tablero.last_movements == []


async def test_sin_datos_coincide_con_los_resumenes(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj_tablero: FrozenClock,
    audit_chain_factory: object,
) -> None:
    tablero = await dashboard_service.summary(session, with_finances=True)
    resumen = await memberships_service.summary(session, today=HOY)
    assert tablero.members_active == resumen.active
    assert (
        tablero.income_month_cop == (await payments_service.summary(session, "2026-10")).total_cop
    )
    assert tablero.last_movements == []


# Coach sin finanzas (S4A-D118) ----------------------------------------------------------------


async def test_el_coach_recibe_los_mismos_conteos_sin_ingresos_y_sin_consultar_pagos(
    session: AsyncSession, datos: None, contador_de_consultas: ContadorDeConsultas
) -> None:
    admin = await dashboard_service.summary(session, with_finances=True)
    with contador_de_consultas.midiendo() as contador:
        coach = await dashboard_service.summary(session, with_finances=False)
    assert coach.income_month_cop is None
    assert admin.income_month_cop == INGRESOS_DE_OCTUBRE
    assert coach.model_dump(exclude={"income_month_cop"}) == admin.model_dump(
        exclude={"income_month_cop"}
    )
    assert contador.de("payments.payments") == 0, contador.sentencias
    cuerpo = coach.model_dump(mode="json")
    assert set(cuerpo) == CAMPOS_DASHBOARD
    assert cuerpo["income_month_cop"] is None
