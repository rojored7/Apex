"""El recálculo diario frente a las escrituras del mismo socio (S4A-B2; S4A-D2, D3, S3-D43).

Molde de `test_lock_order.py`: `dos_sesiones` (commit real) con `SET LOCAL lock_timeout = '2s'`
para la operación del api, y el recálculo (`recompute_statuses`) con su propia fábrica sobre un
motor con `lock_timeout` de 2 s (una transacción por socio, como en el worker). Las dos corren a
la vez con `asyncio.gather`.

Escenario común: el socio tiene una `active` del 1 al 26 de octubre (hoy, 21 de octubre, faltan 5
días: el recálculo la pasa a `expiring`). Frente a:
- `freeze` del 21 al 30: las dos terminan bien; queda `frozen` (la congelación contiene hoy);
- `cancel`: las dos terminan bien; **la anulación gana**: queda `cancelled` en cualquier orden;
- `sell` sin `renew`: choca con la vigente (409 `membership_conflict`) en cualquier orden;
- `register` de 60.000: las dos terminan bien.
Ninguna puede terminar con 55P03 (`DatabaseBusy`) ni 40P01; el recálculo no omite al socio por
ocupación ni cuenta errores. Al final, toda membresía no anulada tiene el estado guardado igual
al efectivo de hoy (paridad).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy, sqlstate_of
from app.core.errors import DomainError
from app.modules.memberships import service
from app.modules.memberships.exceptions import MembershipConflict
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.memberships.rules import FreezeWindow, compute_status, snapshot
from app.modules.memberships.service import RecomputeSummary
from app.modules.payments import service as payments_service
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan

ACTOR = UUID("0000000a-0000-4000-8000-00000000a002")
HOY = date(2026, 10, 21)
SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})
Fabrica = async_sessionmaker[AsyncSession]
Operacion = Callable[[AsyncSession, UUID, UUID], Awaitable[object]]


@pytest.fixture
async def fabrica_del_job(migrated_database: str) -> AsyncIterator[Fabrica]:
    """Sesiones del recálculo con `lock_timeout` de 2 s (como `SET LOCAL` en la otra)."""
    motor = create_async_engine(
        migrated_database,
        hide_parameters=True,
        connect_args={"server_settings": {"lock_timeout": "2s"}},
    )
    try:
        yield async_sessionmaker(motor, expire_on_commit=False)
    finally:
        await motor.dispose()


async def _preparar(sesion: AsyncSession) -> tuple[UUID, UUID, UUID]:
    """`(member_id, plan_id, membership_id)` de la `active` del 1 al 26 de octubre."""
    socio = await make_member(sesion)
    plan = await make_plan(sesion)
    membresia = await make_membership(
        sesion, socio, plan, status="active", start=date(2026, 10, 1), end=date(2026, 10, 26)
    )
    return socio.id, plan.id, membresia.id


async def _congelar(sesion: AsyncSession, plan_id: UUID, membership_id: UUID) -> object:
    return await service.freeze(
        sesion,
        membership_id=membership_id,
        frozen_from=date(2026, 10, 21),
        frozen_to=date(2026, 10, 30),
    )


async def _anular(sesion: AsyncSession, plan_id: UUID, membership_id: UUID) -> object:
    return await service.cancel(sesion, membership_id=membership_id, reason="Cambio de ciudad")


async def _registrar(sesion: AsyncSession, plan_id: UUID, membership_id: UUID) -> object:
    return await payments_service.register(
        sesion,
        membership_id=membership_id,
        amount_cop=60_000,
        method="cash",
        reference=None,
        paid_at=None,
        role="coach",
    )


COMBINACIONES: dict[str, tuple[str, type[DomainError] | None, str | None]] = {
    # nombre: (operación, error de dominio esperado, estado final guardado esperado)
    "freeze": ("congelar", None, "frozen"),
    "cancel": ("anular", None, "cancelled"),
    "sell": ("vender", MembershipConflict, "expiring"),
    "register": ("registrar", None, "expiring"),
}


async def _operar(
    sesion: AsyncSession, nombre: str, member_id: UUID, plan_id: UUID, membership_id: UUID
) -> object:
    if nombre == "vender":
        return await service.sell(sesion, member_id=member_id, plan_id=plan_id)
    operaciones: dict[str, Operacion] = {
        "congelar": _congelar,
        "anular": _anular,
        "registrar": _registrar,
    }
    return await operaciones[nombre](sesion, plan_id, membership_id)


async def _correr_api(sesion: AsyncSession, nombre: str, ids: tuple[UUID, UUID, UUID]) -> object:
    with actor_scope(ACTOR):
        try:
            await sesion.execute(text("SET LOCAL lock_timeout = '2s'"))
            salida = await _operar(sesion, nombre, *ids)
            await sesion.commit()
        except (DomainError, DBAPIError) as error:
            await sesion.rollback()
            return error
    return salida


async def _correr_job(fabrica: Fabrica) -> RecomputeSummary:
    with actor_scope(SYSTEM_USER_ID):
        return await service.recompute_statuses(fabrica, today=HOY)


async def _paridad(sesion: AsyncSession) -> list[tuple[str, str]]:
    """`(guardado, efectivo)` de cada membresía no anulada cuyo estado difiere."""
    filas = list(await sesion.scalars(select(Membership)))
    ventanas: dict[UUID, list[FreezeWindow]] = {}
    for fila in await sesion.scalars(select(MembershipFreeze)):
        ventanas.setdefault(fila.membership_id, []).append(
            FreezeWindow(fila.frozen_from, fila.frozen_to)
        )
    return [
        (f.status, efectivo.value)
        for f in filas
        if f.status != "cancelled"
        and (efectivo := compute_status(snapshot(f), HOY, 7, ventanas.get(f.id, []))).value
        != f.status
    ]


@pytest.mark.parametrize("orden", ["job-primero", "api-primero"])
@pytest.mark.parametrize("combinacion", sorted(COMBINACIONES))
async def test_el_recalculo_frente_a_una_escritura_del_socio_no_se_bloquea(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    fabrica_del_job: Fabrica,
    combinacion: str,
    orden: str,
) -> None:
    primera, segunda = dos_sesiones
    nombre, error_esperado, estado_final = COMBINACIONES[combinacion]
    ids = await _preparar(primera)
    tareas = [_correr_job(fabrica_del_job), _correr_api(segunda, nombre, ids)]
    if orden == "api-primero":
        tareas.reverse()

    resultados = await asyncio.gather(*tareas, return_exceptions=True)

    resumenes = [r for r in resultados if isinstance(r, RecomputeSummary)]
    assert len(resumenes) == 1, resultados  # el recálculo terminó sin lanzar
    resumen = resumenes[0]
    [del_api] = [r for r in resultados if r is not resumen]
    prohibidos = [
        r
        for r in resultados
        if isinstance(r, DatabaseBusy)
        or (isinstance(r, DBAPIError) and sqlstate_of(r) in SQLSTATES_PROHIBIDOS)
    ]
    assert prohibidos == [], resultados
    assert (resumen.busy_omitidos, resumen.errores) == (0, 0), resumen
    if error_esperado is None:
        assert not isinstance(del_api, BaseException), del_api
    else:
        assert isinstance(del_api, error_esperado), del_api
    estado = await primera.scalar(select(Membership.status).where(Membership.id == ids[2]))
    assert estado == estado_final
    assert await _paridad(primera) == []
    await primera.commit()
