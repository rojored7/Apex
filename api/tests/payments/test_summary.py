"""`payments.service.summary` (S3-B8, US-100; D23, M-4, M-8 punto 3, L-13, S3-D47, S3-D51).

El resumen cuenta por `paid_at` en el mes civil de Bogotá, `[inicio, fin)` de
`rules.month_bounds_utc` (octubre de 2026: `2026-10-01T05:00Z` a `2026-11-01T05:00Z`). Totales
a mano:
- escenario del blueprint (`octubre`): efectivo 300.000 (2026-10-05T15:00Z), Nequi 240.000
  (2026-10-10T15:00Z), Bre-B 120.000 (2026-10-15T15:00Z) y un Nequi de 120.000 anulado
  (2026-10-12T15:00Z): `total_cop` 660.000, `by_method` {300.000, 240.000, 120.000},
  `voided_count` 1, `payments_count` 3;
- bordes: 2026-10-01T04:59:59Z (Bre-B 20.000) es el 30 de septiembre en Bogotá; 2026-10-01T05:00Z
  (Bre-B 10.000) ya es octubre; 2026-11-01T03:00Z (efectivo 50.000) es el 31 de octubre a las
  22:00 en Bogotá; 2026-11-01T05:00Z (Nequi 70.000) es noviembre;
- sin `month`, el mes de `current_clock().today_bogota()`: con el reloj en
  2026-10-31T23:30-05:00 (2026-11-01T04:30Z) es octubre;
- L-13: un pago de septiembre (100.000, 2026-09-20T15:00Z) anulado el 2026-10-21 (hoy) no cambia
  octubre y sí baja septiembre (de 100.000 y 1 pago a 0 y 0, con `voided_count` 1); la suma de
  `list(voided=false)` del mismo rango sigue cuadrando con `total_cop` en los dos meses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.memberships.models import Membership
from app.modules.payments import rules, service
from app.modules.payments.exceptions import InvalidMonth
from app.modules.payments.schemas import PaymentListQuery, PaymentsSummary
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import CAMPOS_POR_MEDIO, CAMPOS_RESUMEN, GateDoble, anular

BOGOTA = ZoneInfo("America/Bogota")
ADMIN = SYSTEM_USER_ID


def _utc(mes: int, dia: int, hora: int = 15, minuto: int = 0, segundo: int = 0) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, segundo, tzinfo=UTC)


@pytest.fixture
async def membresia(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Membership:
    plan = await make_plan(session)
    socio = await make_member(session)
    return await make_membership(session, socio, plan, status="active")


async def _pagar(
    session: AsyncSession,
    membresia: Membership,
    monto: int,
    medio: str,
    cuando: datetime,
    **extra: Any,
) -> Any:
    return await make_payment(
        session, membresia, amount=monto, method=medio, paid_at=cuando, **extra
    )


async def _octubre(session: AsyncSession, membresia: Membership) -> None:
    await _pagar(session, membresia, 300_000, "cash", _utc(10, 5))
    await _pagar(session, membresia, 240_000, "nequi", _utc(10, 10))
    await _pagar(session, membresia, 120_000, "breb", _utc(10, 15))
    await _pagar(session, membresia, 120_000, "nequi", _utc(10, 12), voided=True)


async def resumen(session: AsyncSession, month: str | None = None) -> PaymentsSummary:
    with actor_scope(SYSTEM_USER_ID):
        if month is None:
            return await service.summary(session)
        return await service.summary(session, month=month)


async def suma_de_la_lista(session: AsyncSession, month: str) -> int:
    """La suma de `amount_cop` de `list(voided=false)` del mismo rango (cuadre de la demo 7)."""
    inicio, fin = rules.month_bounds_utc(month)
    total = 0
    offset = 0
    with actor_scope(SYSTEM_USER_ID):
        while True:
            pagina = await service.list(
                session,
                PaymentListQuery.model_validate({"from": inicio, "to": fin, "voided": False}),
                PageParams(limit=200, offset=offset),
            )
            total += sum(fila.amount_cop for fila in pagina.items)
            offset += 200
            if offset >= pagina.total:
                return total


async def test_el_escenario_del_blueprint_da_660_000_por_medio(
    session: AsyncSession, membresia: Membership
) -> None:
    await _octubre(session, membresia)
    salida = await resumen(session, "2026-10")
    assert set(salida.model_dump()) == CAMPOS_RESUMEN
    assert set(salida.by_method.model_dump()) == CAMPOS_POR_MEDIO
    assert salida.month == "2026-10"
    assert salida.total_cop == 660_000
    assert salida.by_method.model_dump() == {"cash": 300_000, "nequi": 240_000, "breb": 120_000}
    assert (salida.voided_count, salida.payments_count) == (1, 3)
    assert all(type(v) is int for v in (salida.total_cop, salida.voided_count))


async def test_los_bordes_del_mes_son_los_de_bogota(
    session: AsyncSession, membresia: Membership
) -> None:
    await _pagar(session, membresia, 20_000, "breb", _utc(10, 1, 4, 59, 59))
    await _pagar(session, membresia, 10_000, "breb", _utc(10, 1, 5))
    await _pagar(session, membresia, 50_000, "cash", _utc(11, 1, 3))
    await _pagar(session, membresia, 70_000, "nequi", _utc(11, 1, 5))
    septiembre = await resumen(session, "2026-09")
    octubre = await resumen(session, "2026-10")
    noviembre = await resumen(session, "2026-11")
    assert (septiembre.total_cop, septiembre.by_method.breb, septiembre.payments_count) == (
        20_000,
        20_000,
        1,
    )
    assert (octubre.total_cop, octubre.payments_count) == (60_000, 2)
    assert octubre.by_method.model_dump() == {"cash": 50_000, "nequi": 0, "breb": 10_000}
    assert (noviembre.total_cop, noviembre.by_method.nequi, noviembre.payments_count) == (
        70_000,
        70_000,
        1,
    )


async def test_un_mes_sin_pagos_da_ceros(session: AsyncSession, membresia: Membership) -> None:
    await _octubre(session, membresia)
    salida = await resumen(session, "2026-03")
    assert salida.month == "2026-03"
    assert (salida.total_cop, salida.voided_count, salida.payments_count) == (0, 0, 0)
    assert salida.by_method.model_dump() == {"cash": 0, "nequi": 0, "breb": 0}


async def test_sin_month_usa_el_mes_de_bogota_del_reloj(
    session: AsyncSession, membresia: Membership, reloj: FrozenClock
) -> None:
    await _pagar(session, membresia, 50_000, "cash", _utc(11, 1, 3))
    await _pagar(session, membresia, 70_000, "nequi", _utc(11, 1, 5))
    reloj.set(datetime(2026, 10, 31, 23, 30, tzinfo=BOGOTA))  # 2026-11-01T04:30Z
    salida = await resumen(session)
    assert salida.month == "2026-10"
    assert (salida.total_cop, salida.payments_count) == (50_000, 1)
    reloj.set(datetime(2026, 11, 1, 0, 0, tzinfo=BOGOTA))
    assert (await resumen(session)).month == "2026-11"


async def test_el_total_cuadra_con_la_suma_de_la_lista_de_vigentes(
    session: AsyncSession, membresia: Membership
) -> None:
    await _octubre(session, membresia)
    await _pagar(session, membresia, 50_000, "cash", _utc(11, 1, 3))  # octubre en Bogotá
    await _pagar(session, membresia, 70_000, "nequi", _utc(11, 1, 5))  # noviembre
    await _pagar(session, membresia, 30_000, "cash", _utc(9, 30), voided=True)  # septiembre
    for mes in ("2026-09", "2026-10", "2026-11"):
        assert (await resumen(session, mes)).total_cop == await suma_de_la_lista(session, mes), mes
    assert (await resumen(session, "2026-10")).total_cop == 710_000


async def test_anular_en_octubre_un_pago_de_septiembre_cambia_septiembre_y_no_octubre(
    session: AsyncSession, membresia: Membership, gate_doble: GateDoble
) -> None:
    """L-13 y M-8 punto 3: el resumen cuenta por `paid_at`; la anulación mueve el mes del pago."""
    await _octubre(session, membresia)
    viejo = await _pagar(session, membresia, 100_000, "cash", _utc(9, 20))
    antes_septiembre = await resumen(session, "2026-09")
    antes_octubre = await resumen(session, "2026-10")
    assert (antes_septiembre.total_cop, antes_septiembre.payments_count) == (100_000, 1)
    assert antes_septiembre.voided_count == 0
    await anular(session, ADMIN, payment_id=viejo.id, reason="Pago de septiembre mal registrado")
    despues_septiembre = await resumen(session, "2026-09")
    assert (despues_septiembre.total_cop, despues_septiembre.payments_count) == (0, 0)
    assert despues_septiembre.voided_count == 1
    assert despues_septiembre.by_method.cash == 0
    assert (await resumen(session, "2026-10")).model_dump() == antes_octubre.model_dump()
    for mes in ("2026-09", "2026-10"):
        assert (await resumen(session, mes)).total_cop == await suma_de_la_lista(session, mes), mes


@pytest.mark.parametrize("mes", ["2026-13", "9999-12", "0000-01", "2019-12", "26-10"])
async def test_un_mes_invalido_es_invalid_month(
    session: AsyncSession, membresia: Membership, mes: str
) -> None:
    with pytest.raises(InvalidMonth) as error:
        await resumen(session, mes)
    assert (error.value.status, error.value.field) == (422, "month")
