"""Revertir la activación al anular un pago (S3-B5, US-087; blueprint B5 y flujo 6.3; D5, D13,
N-25, L-5).

Por el bus REAL: `payments.service.void` emite `PaymentVoided` y `memberships.on_payment_voided`
bloquea la fila (`lock_membership(session, event.membership_id)`), calcula el estado EFECTIVO
(`compute_status` con `hoy = to_bogota_date(event.occurred_at)`, `expiring_days` de la política y
las congelaciones), suma los pagos no anulados (`payments.service.sum_not_voided`: `void` hace
`flush` antes de emitir) y, si `rules.should_revert(efectivo, agreed_price_cop, pagado)`, fija
`status = pending_payment` sin tocar `end_date` ni las congelaciones, deja la auditoría `update`
del admin que anuló y emite una vez `MembershipActivationReverted(membership_id, member_id,
previous_status)` con el estado efectivo previo. `pending_payment`, `expired` (efectivo) y
`cancelled` no cambian.

"Hoy" es 2026-10-21 (`reloj`); `expiring_days = 7`. Valores a mano (precio 120.000, plan de 30
días: el fin es el inicio más 30):
- venta de hoy: del 2026-10-21 al 2026-11-20; 120.000 la activan (`active`); anular ese pago la
  devuelve a `pending_payment` con el mismo fin;
- 120.000 + 20.000 (sobrepago confirmado): anular el de 20.000 deja 120.000, que cubren: sigue
  `active`, sin evento ni auditoría nueva;
- `expiring`: del 2026-09-28 al 2026-10-28 (faltan 7 días, `<= 7`);
- `frozen`: del 2026-10-15 al 2026-11-14 con congelación del 2026-10-20 al 2026-10-25 (contiene
  hoy; la fábrica no corre el fin): anular deja `pending_payment` con la congelación y el fin
  intactos (N-25), y un pago nuevo que cubre la devuelve a `frozen`;
- `expired` efectivo: `active` guardada del 2026-09-01 al 2026-10-01 (vencida hoy): no cambia;
- `cancelled`: no cambia (L-5).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.memberships import service
from app.modules.memberships.models import Membership
from app.modules.memberships.rules import MembershipStatus, should_revert
from app.modules.memberships.service import MembershipActivationReverted
from app.modules.payments import service as payments_service
from tests.conftest import CapturarEventos
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import congelaciones_de, leer_membresia
from tests.payments._apoyo import anular, leer_pago, registrar, updates_de

ADMIN = UUID("0000000a-0000-4000-8000-00000000b520")
PAGADOR = UUID("0000000a-0000-4000-8000-00000000b521")
MOTIVO = "Monto mal digitado"
TABLA = "memberships.memberships"


async def _membresia(session: AsyncSession, **cambios: Any) -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, **cambios)


async def _pagar(
    session: AsyncSession, membership_id: UUID, monto: int = 120_000, referencia: str = "REC-1"
) -> UUID:
    salida = await registrar(
        session,
        PAGADOR,
        membership_id=membership_id,
        amount_cop=monto,
        method="cash",
        reference=referencia,
        confirm_overpayment=True,
    )
    return salida.id


async def _fila(session: AsyncSession, membership_id: UUID) -> dict[str, Any]:
    fila = await leer_membresia(session, membership_id)
    assert fila is not None
    return fila


# Revertir -----------------------------------------------------------------------------------------


async def test_anular_el_unico_pago_devuelve_pending_payment_y_emite_una_vez(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    revertidas = capturar_eventos(MembershipActivationReverted)
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    pago_id = await _pagar(session, membresia_id)
    assert (await _fila(session, membresia_id))["status"] == "active"
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    fila = await _fila(session, membresia_id)
    assert fila["status"] == "pending_payment"
    assert (fila["start_date"], fila["end_date"]) == (date(2026, 10, 21), date(2026, 11, 20))
    assert [(e.membership_id, e.member_id, e.previous_status) for e in revertidas] == [
        (membresia_id, socio_id, "active")
    ]


async def test_la_reversion_deja_un_update_de_estado_del_admin_con_el_socio(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    pago_id = await _pagar(session, membresia_id)
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    cambios = await updates_de(session, TABLA, membresia_id)
    assert [(c["user_id"], c["subject_member_id"]) for c in cambios] == [
        (PAGADOR, socio_id),
        (ADMIN, socio_id),
    ]
    assert (cambios[1]["before"], cambios[1]["after"]) == (
        {"status": "active"},
        {"status": "pending_payment"},
    )


async def test_si_lo_que_queda_cubre_sigue_active_sin_evento(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    revertidas = capturar_eventos(MembershipActivationReverted)
    membresia = await _membresia(session)
    membresia_id = membresia.id
    await _pagar(session, membresia_id, referencia="REC-1")
    extra = await _pagar(session, membresia_id, monto=20_000, referencia="REC-2")
    await anular(session, ADMIN, payment_id=extra, reason=MOTIVO)
    assert (await _fila(session, membresia_id))["status"] == "active"
    assert revertidas == []
    assert len(await updates_de(session, TABLA, membresia_id)) == 1  # solo la activación


async def test_una_expiring_vuelve_a_pending_payment(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    revertidas = capturar_eventos(MembershipActivationReverted)
    membresia = await _membresia(session, start=date(2026, 9, 28))
    assert membresia.end_date == date(2026, 10, 28)
    pago_id = await _pagar(session, membresia.id)
    assert (await _fila(session, membresia.id))["status"] == "expiring"
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    fila = await _fila(session, membresia.id)
    assert (fila["status"], fila["end_date"]) == ("pending_payment", date(2026, 10, 28))
    assert [e.previous_status for e in revertidas] == ["expiring"]


async def test_una_frozen_vuelve_a_pending_payment_con_su_congelacion_y_su_fin(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    revertidas = capturar_eventos(MembershipActivationReverted)
    membresia = await _membresia(session, start=date(2026, 10, 15))
    membresia_id = membresia.id
    await make_freeze(session, membresia, date(2026, 10, 20), date(2026, 10, 25))
    pago_id = await _pagar(session, membresia_id, referencia="REC-1")
    assert (await _fila(session, membresia_id))["status"] == "frozen"
    ventanas_antes = await congelaciones_de(session, membresia_id)
    await anular(session, ADMIN, payment_id=pago_id, reason=MOTIVO)
    fila = await _fila(session, membresia_id)
    assert (fila["status"], fila["end_date"]) == ("pending_payment", date(2026, 11, 14))
    assert await congelaciones_de(session, membresia_id) == ventanas_antes
    assert [e.previous_status for e in revertidas] == ["frozen"]
    await _pagar(session, membresia_id, referencia="REC-2")
    fila = await _fila(session, membresia_id)
    assert (fila["status"], fila["end_date"]) == ("frozen", date(2026, 11, 14))


# No revertir --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("guardado", "inicio"),
    [
        ("active", date(2026, 9, 1)),
        ("cancelled", date(2026, 10, 21)),
        ("pending_payment", date(2026, 10, 21)),
    ],
    ids=["expired-efectiva", "cancelled", "pending-payment"],
)
async def test_expired_cancelled_y_pending_payment_no_cambian(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
    guardado: str,
    inicio: date,
) -> None:
    revertidas = capturar_eventos(MembershipActivationReverted)
    membresia = await _membresia(session, status=guardado, start=inicio)
    membresia_id = membresia.id
    pago = await make_payment(session, membresia, amount=60_000)
    antes = await _fila(session, membresia_id)
    salida = await anular(session, ADMIN, payment_id=pago.id, reason=MOTIVO)
    assert salida.voided is True
    assert await _fila(session, membresia_id) == antes
    assert revertidas == []
    assert await updates_de(session, TABLA, membresia_id) == []


# Atomicidad ---------------------------------------------------------------------------------------


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_de_revertida_que_falla_deja_el_pago_sin_anular_y_la_activa(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id
    pago_id = await _pagar(session, membresia_id)

    async def roto(evento: MembershipActivationReverted, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipActivationReverted, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ADMIN):
        await payments_service.void(session, payment_id=pago_id, reason=MOTIVO)
    pago = await leer_pago(session, pago_id)
    assert pago is not None and pago["voided"] is False
    assert (await _fila(session, membresia_id))["status"] == "active"
    assert len(await updates_de(session, TABLA, membresia_id)) == 1  # solo la activación


def test_el_handler_esta_suscrito_a_payment_voided() -> None:
    suscritos = events.subscribers_for(payments_service.PaymentVoided)
    assert service.on_payment_voided in suscritos


# Regla pura (D13) ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("efectivo", "pactado", "pagado", "esperado"),
    [
        (MembershipStatus.active, 120_000, 0, True),
        (MembershipStatus.active, 120_000, 119_999, True),
        (MembershipStatus.expiring, 120_000, 60_000, True),
        (MembershipStatus.frozen, 120_000, 0, True),
        (MembershipStatus.active, 120_000, 120_000, False),
        (MembershipStatus.active, 120_000, 150_000, False),
        (MembershipStatus.frozen, 120_000, 120_000, False),
        (MembershipStatus.pending_payment, 120_000, 0, False),
        (MembershipStatus.expired, 120_000, 0, False),
        (MembershipStatus.cancelled, 120_000, 0, False),
    ],
)
def test_should_revert(
    efectivo: MembershipStatus, pactado: int, pagado: int, esperado: bool
) -> None:
    assert should_revert(efectivo, pactado, pagado) is esperado
