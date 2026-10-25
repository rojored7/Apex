"""Orden único de candados (S3-B1; H-3 punto 3, S3-D43, D3).

Cada combinación corre las dos operaciones a la vez con `dos_sesiones` (commit real) y
`SET LOCAL lock_timeout = '2s'` en las dos transacciones: si el orden de D3 (socio, `FOR SHARE`
del plan, fila de la membresía, fila del pago, cadena de auditoría) se rompiera, una terminaría
con 55P03 (espera agotada, `DatabaseBusy`) o 40P01 (interbloqueo). Ninguna puede terminar así:
la segunda espera el candado del socio, ve lo que confirmó la primera y responde con su error de
dominio.

B1 trae `sell`/`sell`; B2 `freeze`/`sell` (el socio tiene una `active` del 1 al 31 de octubre: la
congelación del 21 al 30 corre su fin y la venta sin `renew` choca con la vigente, 409
`membership_conflict`, en cualquier orden); B3 `sell`/`register` (el mismo socio: un pago de
60.000 sobre su `active` del 1 al 31 de octubre mientras se le vende otra; el pago toma la fila de
esa membresía por el gate y la venta el candado del socio, sin cruzarse: el pago entra y la venta
choca con la vigente, 409 `membership_conflict`); B4 a B6 y B10 agregan `register`/`void`,
`freeze`/`register`, `sell`/`cancel` y `sell`/`deactivate` a `COMBINACIONES`.

El gate de pagos es el doble de `tests/payments/_apoyo.py` (`GateDoble`, `FOR UPDATE` sobre la fila
real) mientras el real no exista (B4, E9); se registra en todas las combinaciones (las que no
pagan no lo usan).
Cada combinación declara cómo prepara su escenario (B1: socio y plan; B2: además la membresía).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy, sqlstate_of
from app.core.errors import DomainError
from app.modules.memberships import service
from app.modules.memberships.exceptions import MembershipConflict
from app.modules.payments import service as payments_service
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.payments._apoyo import GateDoble, gate_registrado

ACTOR = UUID("0000000a-0000-4000-8000-00000000a002")
SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})


@dataclass(frozen=True)
class Escenario:
    member_id: UUID
    plan_id: UUID
    membership_id: UUID | None = None


Operacion = Callable[[AsyncSession, Escenario], Awaitable[object]]
Preparar = Callable[[AsyncSession], Awaitable[Escenario]]


async def _socio_y_plan(sesion: AsyncSession) -> Escenario:
    socio = await make_member(sesion)
    plan = await make_plan(sesion)
    return Escenario(member_id=socio.id, plan_id=plan.id)


async def _con_activa(sesion: AsyncSession) -> Escenario:
    """Socio con una `active` del 1 al 31 de octubre (hoy, 21 de octubre, faltan 10 días)."""
    socio = await make_member(sesion)
    plan = await make_plan(sesion)
    membresia = await make_membership(sesion, socio, plan, status="active", start=date(2026, 10, 1))
    return Escenario(member_id=socio.id, plan_id=plan.id, membership_id=membresia.id)


async def _vender(sesion: AsyncSession, escenario: Escenario) -> object:
    return await service.sell(sesion, member_id=escenario.member_id, plan_id=escenario.plan_id)


async def _congelar(sesion: AsyncSession, escenario: Escenario) -> object:
    assert escenario.membership_id is not None
    return await service.freeze(
        sesion,
        membership_id=escenario.membership_id,
        frozen_from=date(2026, 10, 21),
        frozen_to=date(2026, 10, 30),
    )


async def _registrar_pago(sesion: AsyncSession, escenario: Escenario) -> object:
    assert escenario.membership_id is not None
    return await payments_service.register(
        sesion,
        membership_id=escenario.membership_id,
        amount_cop=60_000,
        method="cash",
        reference=None,
        paid_at=None,
        role="coach",
    )


COMBINACIONES: dict[str, tuple[Preparar, Operacion, Operacion, type[DomainError]]] = {
    "sell-sell": (_socio_y_plan, _vender, _vender, MembershipConflict),
    "freeze-sell": (_con_activa, _congelar, _vender, MembershipConflict),
    "sell-register": (_con_activa, _vender, _registrar_pago, MembershipConflict),
}


async def _correr(sesion: AsyncSession, operacion: Operacion, escenario: Escenario) -> object:
    with actor_scope(ACTOR):
        try:
            await sesion.execute(text("SET LOCAL lock_timeout = '2s'"))
            salida = await operacion(sesion, escenario)
            await sesion.commit()
        except (DomainError, DBAPIError) as error:
            await sesion.rollback()
            return error
    return salida


@pytest.mark.parametrize("combinacion", sorted(COMBINACIONES))
async def test_las_combinaciones_terminan_sin_espera_agotada_ni_interbloqueo(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    combinacion: str,
) -> None:
    primera, segunda = dos_sesiones
    preparar, op_a, op_b, error_esperado = COMBINACIONES[combinacion]
    escenario = await preparar(primera)
    with gate_registrado(GateDoble()):
        resultados = await asyncio.gather(
            _correr(primera, op_a, escenario),
            _correr(segunda, op_b, escenario),
            return_exceptions=True,  # las dos terminan antes de que `dos_sesiones` limpie
        )
    inesperados = [
        r for r in resultados if isinstance(r, BaseException) and not isinstance(r, DomainError)
    ]
    assert not [r for r in inesperados if not isinstance(r, DBAPIError)], resultados
    prohibidos = [
        r
        for r in resultados
        if isinstance(r, DatabaseBusy)
        or (isinstance(r, DBAPIError) and sqlstate_of(r) in SQLSTATES_PROHIBIDOS)
    ]
    assert prohibidos == [], resultados
    errores = [r for r in resultados if isinstance(r, DomainError | DBAPIError)]
    assert len(errores) == 1 and isinstance(errores[0], error_esperado), resultados
