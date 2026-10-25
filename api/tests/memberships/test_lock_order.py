"""Orden único de candados (S3-B1; H-3 punto 3, S3-D43, D3).

Cada combinación corre las dos operaciones a la vez con `dos_sesiones` (commit real) y
`SET LOCAL lock_timeout = '2s'` en las dos transacciones: si el orden de D3 (socio, `FOR SHARE`
del plan, fila de la membresía, fila del pago, cadena de auditoría) se rompiera, una terminaría
con 55P03 (espera agotada, `DatabaseBusy`) o 40P01 (interbloqueo). Ninguna puede terminar así:
la segunda espera el candado del socio, ve lo que confirmó la primera y responde con su error de
dominio.

B1 trae `sell`/`sell`; B3 a B6 y B10 agregan `sell`/`register`, `register`/`void`,
`freeze`/`register`, `sell`/`cancel` y `sell`/`deactivate` a `COMBINACIONES`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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
from tests.factories.members import make_member
from tests.factories.plans import make_plan

ACTOR = UUID("0000000a-0000-4000-8000-00000000a002")
SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})


@dataclass(frozen=True)
class Escenario:
    member_id: UUID
    plan_id: UUID


Operacion = Callable[[AsyncSession, Escenario], Awaitable[object]]


async def _vender(sesion: AsyncSession, escenario: Escenario) -> object:
    return await service.sell(sesion, member_id=escenario.member_id, plan_id=escenario.plan_id)


COMBINACIONES: dict[str, tuple[Operacion, Operacion, type[DomainError]]] = {
    "sell-sell": (_vender, _vender, MembershipConflict),
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
    socio = await make_member(primera)
    plan = await make_plan(primera)
    escenario = Escenario(member_id=socio.id, plan_id=plan.id)
    op_a, op_b, error_esperado = COMBINACIONES[combinacion]
    resultados = await asyncio.gather(
        _correr(primera, op_a, escenario), _correr(segunda, op_b, escenario)
    )
    prohibidos = [
        r
        for r in resultados
        if isinstance(r, DatabaseBusy)
        or (isinstance(r, DBAPIError) and sqlstate_of(r) in SQLSTATES_PROHIBIDOS)
    ]
    assert prohibidos == [], resultados
    errores = [r for r in resultados if isinstance(r, DomainError | DBAPIError)]
    assert len(errores) == 1 and isinstance(errores[0], error_esperado), resultados
