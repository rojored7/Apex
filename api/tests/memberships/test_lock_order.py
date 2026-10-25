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
choca con la vigente, 409 `membership_conflict`); B4 `sell` con `first_payment`/`register`
(H-3 punto 3: el socio tiene una `active` del 1 de septiembre al 1 de octubre, vencida hoy; se le
vende otra con su primer pago de 120.000 mientras se registra un pago de 60.000 sobre la vencida,
que acepta pagos por N-28: la venta toma el candado del socio y la fila nueva, el pago la fila
vieja, y las dos terminan bien, sin error de dominio); B5 `register`/`void` (H-3 punto 3, D13: el
socio tiene una `active` de hoy de 120.000 con un pago de 60.000 de la fábrica; se anula ese pago
mientras se registra otro de 60.000 sobre la misma membresía. Las dos piden la fila de la
membresía por el gate y después la del pago (orden membresía, pago), así que se serializan y
terminan bien en cualquier orden: el saldo alcanza para el pago nuevo con o sin la anulación, y
la reversión de la membresía corre en la transacción de `void` sobre la fila que ya tiene); B6
`sell`/`cancel` (H-3 punto 3: el socio tiene una `active` del 1 de septiembre al 1 de octubre,
vencida hoy; el admin la anula mientras se le vende otra desde hoy. `cancel` pide solo la fila
de la vencida (`lock_membership`, nunca el candado del socio) y `sell` el candado del socio y
después inserta: no se cruzan, la vencida no choca con la venta ni anulada ni sin anular, y las
dos terminan bien en cualquier orden) y `freeze`/`register` (S3-D43, pendiente desde B4: la
`active` del 1 al 31 de octubre se congela del 21 al 30 mientras se le registra un pago de
60.000; `freeze` toma el socio y después la fila, `register` la fila por el gate; se serializan
sobre la fila y terminan bien en cualquier orden: el pago no excede el saldo y la membresía no
está `pending_payment`, así que el handler no la cambia). B10 agrega `sell`/`deactivate` (L-1,
S3-D54) en una prueba aparte, porque el resultado depende del orden: las dos toman primero el
candado del socio; si gana la baja, la venta recibe `MemberInactive` (422) y no queda membresía;
si gana la venta, la baja la espera y termina bien, y la fila `insert` de la membresía en la
auditoría va ANTES (`seq` menor) que la fila `update` de la baja. Nunca una venta confirmada
después de la baja, ni 55P03 ni 40P01.

Desde B4 el gate de pagos es el REAL (`memberships.service.membership_payability`, registrado al
importarse `memberships.service`; E9): ya no se usa el doble de `tests/payments/_apoyo.py`.
Cada combinación declara cómo prepara su escenario (B1: socio y plan; B2: además la membresía) y
el error de dominio que espera (`None`: las dos operaciones terminan bien).
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
from app.modules.members import service as members_service
from app.modules.memberships import service
from app.modules.memberships.exceptions import MemberInactive, MembershipConflict
from app.modules.payments import service as payments_service
from app.modules.payments.schemas import PaymentIn
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan

ACTOR = UUID("0000000a-0000-4000-8000-00000000a002")
SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})


@dataclass(frozen=True)
class Escenario:
    member_id: UUID
    plan_id: UUID
    membership_id: UUID | None = None
    payment_id: UUID | None = None


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


async def _con_vencida(sesion: AsyncSession) -> Escenario:
    """Socio con una `active` del 1 de septiembre al 1 de octubre (vencida hoy, 21 de octubre)."""
    socio = await make_member(sesion)
    plan = await make_plan(sesion)
    membresia = await make_membership(sesion, socio, plan, status="active", start=date(2026, 9, 1))
    return Escenario(member_id=socio.id, plan_id=plan.id, membership_id=membresia.id)


async def _con_activa_y_un_pago(sesion: AsyncSession) -> Escenario:
    """Socio con una `active` de hoy de 120.000 y un pago suyo de 60.000 (fábrica, sin eventos)."""
    socio = await make_member(sesion)
    plan = await make_plan(sesion)
    membresia = await make_membership(sesion, socio, plan, status="active")
    pago = await make_payment(sesion, membresia, amount=60_000)
    return Escenario(
        member_id=socio.id, plan_id=plan.id, membership_id=membresia.id, payment_id=pago.id
    )


async def _vender(sesion: AsyncSession, escenario: Escenario) -> object:
    return await service.sell(sesion, member_id=escenario.member_id, plan_id=escenario.plan_id)


async def _vender_con_pago(sesion: AsyncSession, escenario: Escenario) -> object:
    return await service.sell(
        sesion,
        member_id=escenario.member_id,
        plan_id=escenario.plan_id,
        first_payment=PaymentIn(amount_cop=120_000, method="cash"),
        role="coach",
    )


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


async def _anular_membresia(sesion: AsyncSession, escenario: Escenario) -> object:
    assert escenario.membership_id is not None
    return await service.cancel(
        sesion, membership_id=escenario.membership_id, reason="Cambio de ciudad"
    )


async def _anular_pago(sesion: AsyncSession, escenario: Escenario) -> object:
    assert escenario.payment_id is not None
    return await payments_service.void(
        sesion, payment_id=escenario.payment_id, reason="Monto mal digitado"
    )


COMBINACIONES: dict[str, tuple[Preparar, Operacion, Operacion, type[DomainError] | None]] = {
    "sell-sell": (_socio_y_plan, _vender, _vender, MembershipConflict),
    "freeze-sell": (_con_activa, _congelar, _vender, MembershipConflict),
    "sell-register": (_con_activa, _vender, _registrar_pago, MembershipConflict),
    "sell_con_pago-register": (_con_vencida, _vender_con_pago, _registrar_pago, None),
    "register-void": (_con_activa_y_un_pago, _registrar_pago, _anular_pago, None),
    "sell-cancel": (_con_vencida, _vender, _anular_membresia, None),
    "freeze-register": (_con_activa, _congelar, _registrar_pago, None),
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
    if error_esperado is None:
        assert errores == [], resultados
    else:
        assert len(errores) == 1 and isinstance(errores[0], error_esperado), resultados


# S3-B10 (L-1, S3-D54): `sell` frente a `deactivate` ---------------------------------------------


async def _dar_de_baja(sesion: AsyncSession, escenario: Escenario) -> object:
    return await members_service.deactivate(sesion, escenario.member_id)


async def _seq_de(sesion: AsyncSession, tabla: str, accion: str, member_id: UUID) -> list[int]:
    consulta = text(
        "SELECT seq FROM audit.audit_log WHERE table_name = :t AND action = :a "
        "AND subject_member_id = :m ORDER BY seq"
    )
    return list(await sesion.scalars(consulta, {"t": tabla, "a": accion, "m": member_id}))


@pytest.mark.parametrize("orden", ["venta-primero", "baja-primero"])
async def test_sell_frente_a_deactivate_nunca_vende_a_un_dado_de_baja(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    orden: str,
) -> None:
    primera, segunda = dos_sesiones
    escenario = await _socio_y_plan(primera)
    operaciones = (_vender, _dar_de_baja) if orden == "venta-primero" else (_dar_de_baja, _vender)
    resultados = await asyncio.gather(
        _correr(primera, operaciones[0], escenario),
        _correr(segunda, operaciones[1], escenario),
        return_exceptions=True,
    )
    prohibidos = [
        r
        for r in resultados
        if isinstance(r, DatabaseBusy)
        or (isinstance(r, DBAPIError) and sqlstate_of(r) in SQLSTATES_PROHIBIDOS)
    ]
    assert prohibidos == [], resultados
    errores = [r for r in resultados if isinstance(r, BaseException)]
    assert all(isinstance(r, MemberInactive) for r in errores), resultados
    assert len(errores) <= 1, resultados

    ventas = await _seq_de(primera, "memberships.memberships", "insert", escenario.member_id)
    bajas = await _seq_de(primera, "members.members", "update", escenario.member_id)
    await primera.commit()
    assert len(bajas) == 1, (bajas, resultados)  # la baja siempre termina
    if errores:
        assert ventas == [], (ventas, resultados)
    else:
        assert len(ventas) == 1 and ventas[0] < bajas[0], (ventas, bajas, resultados)
