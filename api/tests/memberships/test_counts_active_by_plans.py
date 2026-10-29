"""`memberships.service.counts_active_by_plans` con PostgreSQL real (S4A-B7; S4A-D25).

El conteo de `count_active_by_plan` por lote, para `active_members_count` de `plans`:
- igual a `count_active_by_plan` plan por plan (estado EFECTIVO distinto de `cancelled` y de
  `expired`: cuentan `active`, `expiring`, `pending_payment` y `frozen`);
- todo id pedido aparece: un plan sin ventas (o inexistente) da 0; los repetidos se cuentan una vez;
- sin ids devuelve `{}` sin enviar ninguna sentencia;
- 450 ids van en lotes de `ID_BATCH` (200): tres sentencias sobre `memberships.memberships`;
- no lee la política de settings (como `count_active_by_plan`, `expiring_days` no cambia el
  resultado).
"""

from __future__ import annotations

import math
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.pagination import ID_BATCH
from app.modules.memberships import service
from tests.conftest import ContadorDeConsultas
from tests.factories.plans import make_plan
from tests.memberships._apoyo import TABLA_MEMBRESIAS
from tests.plans._apoyo import con_membresias

TODOS = ["active", "expiring", "pending_payment", "frozen", "expired", "cancelled"]


async def test_es_igual_a_count_active_by_plan_plan_por_plan(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", duration_days=90)
    anual = await make_plan(session, name="Anual", duration_days=365)
    await con_membresias(session, mensual, TODOS)
    await con_membresias(session, trimestral, ["expired", "cancelled", "frozen"])
    await con_membresias(session, anual, ["pending_payment", "pending_payment"])
    ids = [mensual.id, trimestral.id, anual.id]

    conteos = await service.counts_active_by_plans(session, ids)

    assert conteos == {mensual.id: 4, trimestral.id: 1, anual.id: 2}
    for plan_id in ids:
        assert conteos[plan_id] == await service.count_active_by_plan(session, plan_id)


async def test_un_plan_sin_ventas_o_inexistente_da_cero(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    fantasma = uuid4()
    conteos = await service.counts_active_by_plans(session, [plan.id, fantasma])
    assert conteos == {plan.id: 0, fantasma: 0}


async def test_acepta_cualquier_iterable_y_repetidos(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    await con_membresias(session, plan, ["active", "active"])
    conteos = await service.counts_active_by_plans(session, (i for i in [plan.id, plan.id]))
    assert conteos == {plan.id: 2}


async def test_sin_ids_no_consulta(
    session: AsyncSession, reloj: FrozenClock, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo() as medido:
        conteos = await service.counts_active_by_plans(session, [])
    assert conteos == {}
    assert medido.sentencias == []


async def test_450_ids_van_en_lotes_de_id_batch(
    session: AsyncSession,
    reloj: FrozenClock,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    await con_membresias(session, plan, ["active", "expired"])
    ids: list[UUID] = [uuid4() for _ in range(449)] + [plan.id]
    with contador_de_consultas.midiendo() as medido:
        conteos = await service.counts_active_by_plans(session, ids)
    assert len(conteos) == 450
    assert conteos[plan.id] == 1
    assert sum(conteos.values()) == 1
    assert medido.de(TABLA_MEMBRESIAS) == math.ceil(450 / ID_BATCH) == 3
    assert medido.de("settings.settings_sections") == 0


async def test_cuenta_por_estado_efectivo_y_no_por_el_guardado(
    session: AsyncSession, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    """Una `active` guardada que ya venció no cuenta; una congelada hoy sí (D5, N-22)."""
    plan = await make_plan(session)
    await con_membresias(session, plan, ["expired", "frozen"])
    assert await service.counts_active_by_plans(session, [plan.id]) == {plan.id: 1}
