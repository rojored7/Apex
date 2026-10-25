"""`memberships.service.sell` con `first_payment` (S3-B4, US-085; blueprint B4 y flujo 6.1; D3, D4,
D11, H-1, S3-D41, S3-D75, E5).

La venta y su primer pago son una sola unidad dentro del `begin_nested()` de `sell`: después del
`flush` de la membresía y de `emit(MembershipSold)`, `sell` llama a `payments.service.register`
con el gate REAL (`membership_payability`, que toma `FOR UPDATE` de la fila recién insertada),
`confirm_overpayment` del cuerpo y el `role` del llamador; el handler `on_payment_registered`
activa la membresía si el pago cubre el precio, y la respuesta sale con el estado que dejó el
handler, `paid_cop` y `first_payment_id`. Un `DomainError` del pago sale con el `field` prefijado
(`first_payment.<campo>`, `reraise_with_prefix`) y sin dejar nada.

"Hoy" es 2026-10-21 (`reloj`, D33); "ahora" `T0` = 2026-10-21T15:00:00Z. Plan "Mensual" de
120.000 y 30 días: la venta de hoy va del 2026-10-21 al 2026-11-20 (faltan 30 días, más que los
7 de `expiring_days`: `active`). Valores a mano:
- 120.000 cubre: `active`, `paid_cop = 120000`; 60.000 no: `pending_payment`, `paid_cop = 60000`;
- 120.001 sin `confirm_overpayment`: 409 `payment_exceeds_balance` con
  `field="first_payment.amount_cop"` (H-1: el saldo de una venta nueva es el precio del plan) y
  nada en la base; con la confirmación, `active` con una membresía y un pago;
- `paid_at` futuro (T0 + 5 min 1 s): 422 `validation_error` con `field="first_payment.paid_at"`;
  el coach con `paid_at` de hace 8 días (2026-10-13T15:00:00Z): 422 `paid_at_too_retroactive` con
  `field="first_payment.paid_at"`; el admin lo registra;
- una venta que empieza el 2026-11-01 (fin 2026-12-01) con pago completo queda `active`;
- auditoría del socio con el pago completo: `insert` de la membresía, `insert` del pago y
  `update` de la membresía (`status` de `pending_payment` a `active`), las tres del actor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.memberships import service
from app.modules.memberships.service import MembershipActivated, MembershipSold
from app.modules.payments import service as payments_service
from app.modules.payments.exceptions import (
    PaidAtInFuture,
    PaidAtTooRetroactive,
    PaymentExceedsBalance,
)
from app.modules.payments.schemas import PaymentIn
from app.modules.payments.service import MembershipPayability, PaymentRegistered
from tests.conftest import CapturarEventos
from tests.factories.members import make_member, unique_document
from tests.factories.plans import make_plan
from tests.memberships._apoyo import leer_membresia, membresias_del_socio, vender

ACTOR = UUID("0000000a-0000-4000-8000-00000000a401")
T0 = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
HOY = date(2026, 10, 21)


def _pago(**cambios: Any) -> PaymentIn:
    datos: dict[str, Any] = {"amount_cop": 120_000, "method": "cash"}
    datos.update(cambios)
    return PaymentIn(**datos)


async def _socio_y_plan(session: AsyncSession) -> tuple[UUID, UUID]:
    socio = await make_member(session)
    plan = await make_plan(session)
    return socio.id, plan.id


async def _vender(
    session: AsyncSession,
    member_id: UUID,
    plan_id: UUID,
    pago: PaymentIn,
    *,
    role: str | None = "coach",
    **otros: Any,
) -> Any:
    return await vender(
        session, ACTOR, member_id=member_id, plan_id=plan_id, first_payment=pago, role=role, **otros
    )


async def _pagos_del_socio(session: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT id, membership_id, member_id, amount_cop, method, reference, paid_at, "
            "registered_by, created_by FROM payments.payments WHERE member_id = :m "
            "ORDER BY created_at, id"
        ),
        {"m": member_id},
    )
    return [dict(f) for f in filas.mappings().all()]


async def _auditoria_del_socio(session: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    filas = await session.execute(
        text(
            "SELECT table_name, action, record_id, user_id, before, after FROM audit.audit_log "
            "WHERE subject_member_id = :m AND table_name <> 'members.members' ORDER BY seq"
        ),
        {"m": member_id},
    )
    return [dict(f) for f in filas.mappings().all()]


async def _nada_del_socio(session: AsyncSession, member_id: UUID) -> None:
    assert await membresias_del_socio(session, member_id) == []
    assert await _pagos_del_socio(session, member_id) == []
    assert await _auditoria_del_socio(session, member_id) == []


# Venta con pago -----------------------------------------------------------------------------------


async def test_un_pago_igual_al_precio_deja_la_venta_active_en_la_misma_respuesta(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(session, socio_id, plan_id, _pago())
    assert salida.status == "active"
    assert salida.paid_cop == 120_000 and type(salida.paid_cop) is int
    assert salida.agreed_price_cop == 120_000
    assert (salida.start_date, salida.end_date) == (HOY, date(2026, 11, 20))
    pagos = await _pagos_del_socio(session, socio_id)
    assert len(pagos) == 1
    assert salida.first_payment_id == pagos[0]["id"]
    assert pagos[0]["membership_id"] == salida.id
    assert pagos[0]["member_id"] == socio_id  # copiado por el gate (D1)
    assert (pagos[0]["amount_cop"], pagos[0]["method"], pagos[0]["reference"]) == (
        120_000,
        "cash",
        None,
    )
    assert pagos[0]["paid_at"] == T0  # por defecto, "ahora" del reloj
    assert (pagos[0]["registered_by"], pagos[0]["created_by"]) == (ACTOR, ACTOR)
    fila = await leer_membresia(session, salida.id)
    assert fila is not None and fila["status"] == "active"


async def test_un_pago_parcial_deja_la_venta_pending_payment(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(session, socio_id, plan_id, _pago(amount_cop=60_000))
    assert salida.status == "pending_payment"
    assert salida.paid_cop == 60_000
    pagos = await _pagos_del_socio(session, socio_id)
    assert [p["id"] for p in pagos] == [salida.first_payment_id]
    fila = await leer_membresia(session, salida.id)
    assert fila is not None and fila["status"] == "pending_payment"


async def test_paid_at_y_referencia_dados_se_guardan_tal_cual(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    ayer = T0 - timedelta(days=1)
    pago = _pago(method="nequi", reference="NEQ-00123", paid_at=ayer)
    await _vender(session, socio_id, plan_id, pago)
    pagos = await _pagos_del_socio(session, socio_id)
    assert (pagos[0]["method"], pagos[0]["reference"], pagos[0]["paid_at"]) == (
        "nequi",
        "NEQ-00123",
        ayer,
    )


async def test_una_venta_futura_con_pago_completo_queda_active(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(session, socio_id, plan_id, _pago(), start_date=date(2026, 11, 1))
    assert (salida.start_date, salida.end_date) == (date(2026, 11, 1), date(2026, 12, 1))
    assert salida.status == "active"


async def test_sin_primer_pago_la_venta_sigue_como_en_b1(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await vender(session, ACTOR, member_id=socio_id, plan_id=plan_id)
    assert (salida.status, salida.paid_cop, salida.first_payment_id) == ("pending_payment", 0, None)
    assert await _pagos_del_socio(session, socio_id) == []


# Auditoría y eventos ------------------------------------------------------------------------------


async def test_la_auditoria_tiene_dos_insert_y_el_update_de_la_activacion_del_actor(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(session, socio_id, plan_id, _pago())
    filas = await _auditoria_del_socio(session, socio_id)
    assert [(f["table_name"], f["action"], f["record_id"], f["user_id"]) for f in filas] == [
        ("memberships.memberships", "insert", salida.id, ACTOR),
        ("payments.payments", "insert", salida.first_payment_id, ACTOR),
        ("memberships.memberships", "update", salida.id, ACTOR),
    ]
    assert filas[2]["before"] == {"status": "pending_payment"}
    assert filas[2]["after"] == {"status": "active"}


async def test_con_pago_parcial_solo_quedan_los_dos_insert(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    await _vender(session, socio_id, plan_id, _pago(amount_cop=60_000))
    filas = await _auditoria_del_socio(session, socio_id)
    assert [(f["table_name"], f["action"], f["user_id"]) for f in filas] == [
        ("memberships.memberships", "insert", ACTOR),
        ("payments.payments", "insert", ACTOR),
    ]


async def test_la_venta_pagada_emite_vendida_registrado_y_activada_una_vez(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(MembershipSold, PaymentRegistered, MembershipActivated)
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(session, socio_id, plan_id, _pago())
    # El capturador de `PaymentRegistered` corre después de `on_payment_registered` (se suscribió
    # después), así que `MembershipActivated` llega antes; se compara por tipo, no por orden.
    por_tipo = {
        tipo: [e for e in recibidos if type(e) is tipo]
        for tipo in (MembershipSold, PaymentRegistered, MembershipActivated)
    }
    assert {tipo: len(lista) for tipo, lista in por_tipo.items()} == dict.fromkeys(por_tipo, 1)
    assert type(recibidos[0]) is MembershipSold
    [registrado], [activada] = por_tipo[PaymentRegistered], por_tipo[MembershipActivated]
    assert (registrado.membership_id, registrado.payment_id, registrado.amount_cop) == (
        salida.id,
        salida.first_payment_id,
        120_000,
    )
    assert (activada.membership_id, activada.member_id, activada.status) == (
        salida.id,
        socio_id,
        "active",
    )


async def test_la_venta_con_pago_parcial_no_emite_activada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    activadas = capturar_eventos(MembershipActivated)
    socio_id, plan_id = await _socio_y_plan(session)
    await _vender(session, socio_id, plan_id, _pago(amount_cop=60_000))
    assert activadas == []


# Atomicidad (D3) ----------------------------------------------------------------------------------


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


@pytest.mark.parametrize(
    "evento", [PaymentRegistered, MembershipActivated], ids=["registrado", "activada"]
)
async def test_un_handler_que_falla_no_deja_membresia_ni_pago_ni_auditoria(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, evento: type[Any]
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)

    async def roto(recibido: Any, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(evento, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ACTOR):
        await service.sell(
            session, member_id=socio_id, plan_id=plan_id, first_payment=_pago(), role="coach"
        )
    await _nada_del_socio(session, socio_id)


class _GateRoto(Exception):
    """El gate falló (no es un `DomainError`: sale intacto, sin prefijo)."""


async def test_un_gate_que_falla_no_deja_membresia_ni_pago_ni_auditoria(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)

    async def gate_roto(sesion: AsyncSession, membership_id: UUID) -> MembershipPayability:
        raise _GateRoto

    anterior = payments_service.membership_gate()
    payments_service.set_membership_gate(gate_roto)
    try:
        with pytest.raises(_GateRoto), actor_scope(ACTOR):
            await service.sell(
                session, member_id=socio_id, plan_id=plan_id, first_payment=_pago(), role="coach"
            )
    finally:
        payments_service.set_membership_gate(anterior)
    await _nada_del_socio(session, socio_id)


# Errores del pago con el campo prefijado (E5, S3-D75) ---------------------------------------------


async def test_un_pago_mayor_al_precio_sin_confirmar_es_409_en_first_payment_amount_cop(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    with pytest.raises(PaymentExceedsBalance) as error:
        await _vender(session, socio_id, plan_id, _pago(amount_cop=120_001))
    assert type(error.value) is PaymentExceedsBalance
    assert (error.value.code, error.value.status) == ("payment_exceeds_balance", 409)
    assert error.value.field == "first_payment.amount_cop"
    await _nada_del_socio(session, socio_id)


async def test_con_confirm_overpayment_el_sobrepago_queda_active_sin_filas_extra(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    salida = await _vender(
        session, socio_id, plan_id, _pago(amount_cop=120_001, confirm_overpayment=True)
    )
    assert (salida.status, salida.paid_cop) == ("active", 120_001)
    assert len(await membresias_del_socio(session, socio_id)) == 1
    assert len(await _pagos_del_socio(session, socio_id)) == 1


async def test_paid_at_futuro_es_422_en_first_payment_paid_at(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    futuro = T0 + timedelta(minutes=5, seconds=1)
    with pytest.raises(PaidAtInFuture) as error:
        await _vender(session, socio_id, plan_id, _pago(paid_at=futuro))
    assert (error.value.code, error.value.status) == ("validation_error", 422)
    assert error.value.field == "first_payment.paid_at"
    await _nada_del_socio(session, socio_id)


async def test_el_rol_del_llamador_decide_la_retroactividad_del_primer_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan_id = await _socio_y_plan(session)
    hace_8_dias = T0 - timedelta(days=8)
    with pytest.raises(PaidAtTooRetroactive) as error:
        await _vender(session, socio_id, plan_id, _pago(paid_at=hace_8_dias), role="coach")
    assert (error.value.code, error.value.field) == (
        "paid_at_too_retroactive",
        "first_payment.paid_at",
    )
    await _nada_del_socio(session, socio_id)
    salida = await _vender(session, socio_id, plan_id, _pago(paid_at=hace_8_dias), role="admin")
    assert salida.status == "active"
    assert (await _pagos_del_socio(session, socio_id))[0]["paid_at"] == hace_8_dias


async def test_dos_ventas_con_el_mismo_pago_a_dos_socios_no_son_duplicado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """`confirm_duplicate` no aplica a la venta (H-1 punto 4): cada venta es una membresía nueva."""
    plan = await make_plan(session)
    primero = await make_member(session)
    segundo = await make_member(session, document=unique_document(), phone=None, email=None)
    pago = _pago(method="nequi", reference="NEQ-1")
    uno = await _vender(session, primero.id, plan.id, pago)
    dos = await _vender(session, segundo.id, plan.id, pago)
    assert (uno.status, dos.status) == ("active", "active")
    assert uno.first_payment_id != dos.first_payment_id


async def test_sin_rol_el_primer_pago_tiene_el_tope_retroactivo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """S3-D81 (PM5 de Fase 4 quita el centinela `LIMITED_ROLE`): `role=None` no es `admin`."""
    socio_id, plan_id = await _socio_y_plan(session)
    hace_8_dias = T0 - timedelta(days=8)
    with pytest.raises(PaidAtTooRetroactive) as error:
        await _vender(session, socio_id, plan_id, _pago(paid_at=hace_8_dias), role=None)
    assert error.value.field == "first_payment.paid_at"
    await _nada_del_socio(session, socio_id)
