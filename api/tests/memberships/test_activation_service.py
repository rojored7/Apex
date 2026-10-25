"""Activación por cobertura (S3-B4, US-086; blueprint B4 y flujo 6.2; D3, D5, D10, D11).

Por el bus REAL: `payments.service.register` (con el gate real, `membership_payability`) emite
`PaymentRegistered` y `memberships.on_payment_registered` bloquea la fila
(`lock_membership(session, event.membership_id)`), suma los pagos no anulados
(`payments.service.sum_not_voided`, nunca `event.amount_cop`) y, si la membresía estaba
`pending_payment` y `covers(agreed_price_cop, pagado)`, fija `status = compute_status(base activa,
hoy, expiring_days, congelaciones)` con `hoy = to_bogota_date(event.occurred_at)`, deja la
auditoría `update` (`before.status`/`after.status`) del usuario que pagó y emite una vez
`MembershipActivated(membership_id, member_id, status)`. Sobre una membresía que no está
`pending_payment` el handler no cambia nada ni emite.

"Hoy" es 2026-10-21 (`reloj`, D33); `expiring_days = 7` (política por defecto). Valores a mano:
- precio 120.000: 60.000 deja `pending_payment` (sin eventos); 60.000 + 60.000 = 120.000 cubre
  (Q5: pagar de más también) y da `active` (la venta del 2026-10-21 termina el 2026-11-20: faltan
  30 días);
- `expiring`: membresía del 2026-10-04 al 2026-11-03; con el `reloj` en 2026-10-27T15:00:00Z
  (10:00 en Bogotá) faltan 7 días (`<= 7`): `expiring`; el 2026-10-26 faltan 8: `active`;
- un pago anulado de 120.000 (fábrica) no suma: 60.000 vigentes siguen sin cubrir;
- congelación del 2026-10-20 al 2026-10-25 (contiene hoy): el pago que cubre deja `frozen`;
- `pending_payment` del 2026-09-01 al 2026-10-01 (vencida por fecha): el pago que cubre la deja
  `expired` (D11: "pagada y vencida", caso aceptado) y el evento lleva ese estado;
- dos pagos de 60.000 a la vez (`dos_sesiones`, referencias distintas para no ser duplicado): el
  candado de la fila los serializa y la membresía termina `active` con un solo
  `MembershipActivated`.

Los dos pagos seguidos de una misma prueba llevan referencias distintas (`REC-1`, `REC-2`): con la
misma, el segundo sería `payment_possible_duplicate` (H-1).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.errors import DomainError
from app.modules.memberships import lifecycle, service
from app.modules.memberships.models import Membership
from app.modules.memberships.rules import MembershipSnapshot, MembershipStatus
from app.modules.memberships.service import MembershipActivated
from app.modules.payments import service as payments_service
from tests.conftest import CapturarEventos
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import congelar, leer_membresia
from tests.payments._apoyo import pagos_de, registrar

PAGADOR = UUID("0000000a-0000-4000-8000-00000000a402")
TABLA = "memberships.memberships"


async def _membresia(session: AsyncSession, **cambios: Any) -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, **cambios)


async def _pagar(
    session: AsyncSession, membership_id: UUID, monto: int = 60_000, referencia: str = "REC-1"
) -> Any:
    return await registrar(
        session,
        PAGADOR,
        membership_id=membership_id,
        amount_cop=monto,
        method="cash",
        reference=referencia,
    )


async def _estado(session: AsyncSession, membership_id: UUID) -> str:
    fila = await leer_membresia(session, membership_id)
    assert fila is not None
    return str(fila["status"])


async def _cambios_de_estado(session: AsyncSession, membership_id: UUID) -> list[dict[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT user_id, subject_member_id, before, after FROM audit.audit_log "
            "WHERE table_name = :t AND record_id = :r AND action = 'update' ORDER BY seq"
        ),
        {"t": TABLA, "r": membership_id},
    )
    return [dict(f) for f in filas.mappings().all()]


# Cobertura ----------------------------------------------------------------------------------------


async def test_dos_pagos_de_60000_cubren_120000_y_activan_una_sola_vez(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    await _pagar(session, membresia_id, referencia="REC-1")
    assert await _estado(session, membresia_id) == "pending_payment"
    assert activadas == []
    await _pagar(session, membresia_id, referencia="REC-2")
    assert await _estado(session, membresia_id) == "active"
    assert len(activadas) == 1
    evento = activadas[0]
    assert (evento.membership_id, evento.member_id, evento.status) == (
        membresia_id,
        socio_id,
        "active",
    )


async def test_un_pago_de_20000_deja_pending_payment_sin_eventos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session)
    await _pagar(session, membresia.id, monto=20_000)
    assert await _estado(session, membresia.id) == "pending_payment"
    assert activadas == []
    assert await _cambios_de_estado(session, membresia.id) == []


async def test_pagar_de_mas_tambien_cubre(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await registrar(
        session,
        PAGADOR,
        membership_id=membresia.id,
        amount_cop=150_000,
        method="cash",
        confirm_overpayment=True,
    )
    assert await _estado(session, membresia.id) == "active"


async def test_un_pago_anulado_no_suma_para_la_cobertura(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=120_000, voided=True)
    await _pagar(session, membresia.id)
    assert await _estado(session, membresia.id) == "pending_payment"
    assert activadas == []


async def test_el_handler_suma_los_pagos_y_no_confia_en_el_monto_del_evento(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Un pago previo de 60.000 (fábrica, sin evento) más 60.000 por `register`: el evento dice
    60.000, pero la suma es 120.000 y cubre."""
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=60_000)
    await _pagar(session, membresia.id)
    assert await _estado(session, membresia.id) == "active"


# Estado efectivo al activar (D5, D11) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "esperado"),
    [
        (datetime(2026, 10, 27, 15, 0, tzinfo=UTC), "expiring"),
        (datetime(2026, 10, 26, 15, 0, tzinfo=UTC), "active"),
    ],
    ids=["27-oct-faltan-7", "26-oct-faltan-8"],
)
async def test_el_estado_al_activar_sale_del_reloj_y_de_expiring_days(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
    instante: datetime,
    esperado: str,
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session, start=date(2026, 10, 4))
    assert membresia.end_date == date(2026, 11, 3)
    reloj.set(instante)
    await _pagar(session, membresia.id, referencia="REC-1")
    await _pagar(session, membresia.id, referencia="REC-2")
    assert await _estado(session, membresia.id) == esperado
    assert [e.status for e in activadas] == [esperado]


async def test_con_una_congelacion_que_contiene_hoy_el_pago_que_cubre_deja_frozen(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session, start=date(2026, 10, 15))
    await make_freeze(session, membresia, date(2026, 10, 20), date(2026, 10, 25))
    await _pagar(session, membresia.id, monto=120_000)
    assert await _estado(session, membresia.id) == "frozen"


async def test_una_pendiente_ya_vencida_queda_expired_al_pagarse(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session, start=date(2026, 9, 1))
    await _pagar(session, membresia.id, monto=120_000)
    assert await _estado(session, membresia.id) == "expired"
    assert [e.status for e in activadas] == ["expired"]


# Solo `pending_payment` se activa -----------------------------------------------------------------


@pytest.mark.parametrize("estado", ["active", "expiring", "frozen"])
async def test_un_pago_sobre_una_que_no_esta_pendiente_no_cambia_nada_ni_emite(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
    estado: str,
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    membresia = await _membresia(session, status=estado, start=date(2026, 10, 15))
    if estado == "frozen":
        await make_freeze(session, membresia, date(2026, 10, 20), date(2026, 10, 25))
    await _pagar(session, membresia.id, monto=120_000)
    assert await _estado(session, membresia.id) == estado
    assert activadas == []
    assert await _cambios_de_estado(session, membresia.id) == []


# Auditoría y atomicidad (D3) ----------------------------------------------------------------------


async def test_la_activacion_deja_un_update_de_estado_del_usuario_que_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    await _pagar(session, membresia_id, monto=120_000)
    cambios = await _cambios_de_estado(session, membresia_id)
    assert [(c["user_id"], c["subject_member_id"]) for c in cambios] == [(PAGADOR, socio_id)]
    assert cambios[0]["before"] == {"status": "pending_payment"}
    assert cambios[0]["after"] == {"status": "active"}


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_de_activada_que_falla_revierte_el_pago_y_el_estado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    membresia_id = membresia.id

    async def roto(evento: MembershipActivated, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipActivated, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(PAGADOR):
        await payments_service.register(
            session, membership_id=membresia_id, amount_cop=120_000, method="cash", role="coach"
        )
    assert await _estado(session, membresia_id) == "pending_payment"
    assert await pagos_de(session, membresia_id) == []
    assert await _cambios_de_estado(session, membresia_id) == []


def test_el_handler_esta_suscrito_a_payment_registered() -> None:
    suscritos = events.subscribers_for(payments_service.PaymentRegistered)
    assert service.on_payment_registered in suscritos


def test_snapshot_lee_la_fila_sin_cambiarla() -> None:
    fila = Membership(
        member_id=UUID("0000000a-0000-4000-8000-00000000a403"),
        plan_id=UUID("0000000a-0000-4000-8000-00000000a404"),
        agreed_price_cop=120_000,
        start_date=date(2026, 10, 21),
        end_date=date(2026, 11, 20),
        classes_total=12,
        classes_remaining=5,
        status="pending_payment",
    )
    assert lifecycle.snapshot(fila) == MembershipSnapshot(
        id=fila.id,
        status=MembershipStatus.pending_payment,
        start_date=date(2026, 10, 21),
        end_date=date(2026, 11, 20),
        classes_remaining=5,
    )
    assert fila.status == "pending_payment"


# Lo pagado en la salida (B4: `paid_cop` deja de ser 0) --------------------------------------------


async def test_congelar_una_pagada_devuelve_paid_cop_con_lo_no_anulado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """B2 dejó `paid_cop = 0` en `membership_out` "hasta B4": con 120.000 pagados (y 30.000
    anulados que no cuentan) la congelación responde 120.000."""
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=30_000, voided=True)
    await _pagar(session, membresia.id, monto=120_000)
    salida = await congelar(
        session,
        PAGADOR,
        membership_id=membresia.id,
        frozen_from=date(2026, 10, 21),
        frozen_to=date(2026, 10, 30),
    )
    assert (salida.status, salida.paid_cop) == ("frozen", 120_000)


# Concurrencia (D3, con commit real) ---------------------------------------------------------------


async def _intentar(sesion: AsyncSession, membership_id: UUID, referencia: str) -> object:
    with actor_scope(PAGADOR):
        try:
            salida = await payments_service.register(
                sesion,
                membership_id=membership_id,
                amount_cop=60_000,
                method="cash",
                reference=referencia,
                role="coach",
            )
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_pagos_concurrentes_de_60000_terminan_active(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    primera, segunda = dos_sesiones
    membresia = await _membresia(primera)
    membresia_id = membresia.id
    resultados = await asyncio.gather(
        _intentar(primera, membresia_id, "REC-1"),
        _intentar(segunda, membresia_id, "REC-2"),
        return_exceptions=True,  # las dos terminan antes de que `dos_sesiones` limpie
    )
    assert not [r for r in resultados if isinstance(r, BaseException)], resultados
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        assert len(await pagos_de(lectora, membresia_id)) == 2
        assert await _estado(lectora, membresia_id) == "active"
    assert len(activadas) == 1
