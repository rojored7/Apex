"""`payments.service.register` con el doble del gate (S3-B3, US-095; D1, D3, D11, H-1, H-2, M-8).

El gate real lo registra `memberships` en B4 (E9): aquí todas las pruebas usan `gate_doble`, que
bloquea la fila REAL de `memberships.memberships` con `FOR UPDATE` y arma `MembershipPayability`
con su socio, su estado y su precio pactado (S3-D74).

"Ahora" es `T0` = 2026-10-21T15:00:00Z (`reloj`, D33). La membresía de base es la venta del
plan "Mensual" de 120.000 (`make_membership`, `pending_payment`, 2026-10-21 a 2026-11-20).
Valores a mano:
- saldo: con 60.000 ya pagados (fábrica) quedan 60.000; 60.000 pasa, 60.001 sin confirmar es 409
  `payment_exceeds_balance` (`field="amount_cop"`) y con `confirm_overpayment=True` se registra;
- duplicado: mismo usuario, monto, medio y referencia en los últimos 120 s (fábrica con
  `created_at` = 14:58:01Z, 119 s, es duplicado; 14:57:59Z, 121 s, no); dos registros seguidos por
  el service también (el `created_at` del primero sale del reloj de la base, que va por delante
  del `reloj` congelado: la ventana solo tiene piso, ver `test_rules.py`);
- tope: 60 pagos no anulados de 1.000 sobre una membresía de 1.000.000 (saldo de sobra): el 61 es
  409 `payment_limit_reached`; con 59 vigentes y uno anulado, el siguiente se registra;
- retroactividad: el coach con `paid_at` = 2026-10-13T15:00:00Z (8 días) es 422
  `paid_at_too_retroactive`; el admin lo registra; con `max_retroactive_days = 3` guardado en
  settings, 2026-10-17T14:00:00Z (4 días y 1 hora) ya es retroactivo para el coach.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.errors import DomainError
from app.core.pagination import ID_BATCH
from app.modules.memberships.models import Membership
from app.modules.payments import service
from app.modules.payments.exceptions import (
    MembershipCancelled,
    MembershipGateNotRegistered,
    PaidAtInFuture,
    PaidAtTooRetroactive,
    PaymentExceedsBalance,
    PaymentLimitReached,
    PaymentMembershipNotFound,
    PossibleDuplicatePayment,
)
from app.modules.payments.service import MembershipPayability, PaymentRegistered
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import SectionKey
from tests.conftest import CapturarEventos
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import (
    CAMPOS_PAYMENT,
    GateDoble,
    leer_auditoria_de_pagos,
    leer_pago,
    pagos_de,
    registrar,
)

ACTOR = UUID("0000000a-0000-4000-8000-00000000b101")
OTRO_ACTOR = UUID("0000000a-0000-4000-8000-00000000b102")
T0 = datetime(2026, 10, 21, 15, 0, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("gate_doble")


async def _membresia(session: AsyncSession, **cambios: Any) -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, **cambios)


def _pago(membresia: Membership, **cambios: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "membership_id": membresia.id,
        "amount_cop": 60_000,
        "method": "nequi",
        "reference": "NEQ-00123",
        "paid_at": None,
    }
    datos.update(cambios)
    return datos


async def _contar_pagos(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM payments.payments")) or 0)


# Registro feliz --------------------------------------------------------------------------------


async def test_registro_feliz_guarda_la_fila_con_el_actor_y_el_socio_del_gate(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, gate_doble: GateDoble
) -> None:
    membresia = await _membresia(session)
    salida = await registrar(session, ACTOR, **_pago(membresia))
    assert set(salida.model_dump()) == CAMPOS_PAYMENT
    assert (salida.membership_id, salida.member_id) == (membresia.id, membresia.member_id)
    assert (salida.amount_cop, salida.method, salida.reference) == (60_000, "nequi", "NEQ-00123")
    assert type(salida.amount_cop) is int
    assert salida.paid_at == T0  # por defecto, "ahora" del reloj
    assert (salida.registered_by, salida.voided) == (ACTOR, False)
    assert (salida.void_reason, salida.voided_by, salida.voided_at) == (None, None, None)
    fila = await leer_pago(session, salida.id)
    assert fila is not None
    assert (fila["registered_by"], fila["created_by"]) == (ACTOR, ACTOR)
    assert fila["member_id"] == membresia.member_id
    assert (fila["amount_cop"], fila["paid_at"], fila["voided"]) == (60_000, T0, False)
    assert gate_doble.llamadas == [membresia.id]


async def test_paid_at_dado_se_guarda_tal_cual(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    ayer = T0 - timedelta(days=1)
    salida = await registrar(session, ACTOR, **_pago(membresia, paid_at=ayer, reference=None))
    fila = await leer_pago(session, salida.id)
    assert fila is not None and (fila["paid_at"], fila["reference"]) == (ayer, None)


async def test_las_confirmaciones_no_se_guardan(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await registrar(
        session, ACTOR, **_pago(membresia), confirm_overpayment=True, confirm_duplicate=True
    )
    columnas = await session.scalars(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'payments' AND table_name = 'payments'"
        )
    )
    assert not [c for c in columnas if c.startswith("confirm")]


# Gate (D1, N-28) ----------------------------------------------------------------------------------


async def test_membresia_inexistente_es_404_sin_fila(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    with pytest.raises(PaymentMembershipNotFound) as error:
        await registrar(session, ACTOR, membership_id=uuid4(), amount_cop=1_000, method="cash")
    assert (error.value.status, error.value.code) == (404, "membership_not_found")
    assert await _contar_pagos(session) == 0


async def test_membresia_cancelada_es_409_sin_fila(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session, status="cancelled")
    with pytest.raises(MembershipCancelled) as error:
        await registrar(session, ACTOR, **_pago(membresia))
    assert (error.value.status, error.value.code) == (409, "membership_cancelled")
    assert await pagos_de(session, membresia.id) == []
    assert await leer_auditoria_de_pagos(session) == []


@pytest.mark.parametrize("estado", ["expired", "frozen", "active", "expiring"])
async def test_vencidas_congeladas_y_vigentes_reciben_pagos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, estado: str
) -> None:
    """N-28: solo la anulada no recibe pagos."""
    membresia = await _membresia(session, status=estado, start=date(2026, 9, 1))
    salida = await registrar(session, ACTOR, **_pago(membresia))
    assert len(await pagos_de(session, membresia.id)) == 1
    assert salida.member_id == membresia.member_id


async def test_el_socio_y_el_precio_salen_del_gate(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, gate_doble: GateDoble
) -> None:
    """`member_id` se copia de lo que dice el gate (D1), no de otra lectura."""
    membresia = await _membresia(session)
    otro_socio = uuid4()
    gate_doble.forzados[membresia.id] = MembershipPayability(
        exists=True, cancelled=False, member_id=otro_socio, agreed_price_cop=1_000_000
    )
    salida = await registrar(session, ACTOR, **_pago(membresia, amount_cop=500_000))
    assert salida.member_id == otro_socio


async def test_sin_gate_falla_cerrado_y_no_escribe(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    anterior = service.membership_gate()
    service.set_membership_gate(None)
    try:
        with pytest.raises(MembershipGateNotRegistered), actor_scope(ACTOR):
            await service.register(session, **_pago(membresia), role="coach")
    finally:
        service.set_membership_gate(anterior)
    assert await pagos_de(session, membresia.id) == []
    assert await leer_auditoria_de_pagos(session) == []


# Evento, auditoría y atomicidad (D3, D11) --------------------------------------------------------


async def test_emite_payment_registered_una_vez_con_el_monto(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(PaymentRegistered)
    membresia = await _membresia(session)
    salida = await registrar(session, ACTOR, **_pago(membresia))
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert (evento.membership_id, evento.payment_id, evento.amount_cop) == (
        membresia.id,
        salida.id,
        60_000,
    )


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_que_falla_no_deja_pago_ni_auditoria(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)

    async def roto(evento: PaymentRegistered, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(PaymentRegistered, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ACTOR):
        await service.register(session, **_pago(membresia), role="coach")
    assert await pagos_de(session, membresia.id) == []
    assert await leer_auditoria_de_pagos(session) == []


async def test_la_suma_del_handler_ya_ve_el_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """D11: el evento sale tras el `flush`; un suscriptor que suma ve el pago recién insertado."""
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=20_000)
    vistas: list[int] = []

    async def sumar(evento: PaymentRegistered, sesion: AsyncSession) -> None:
        vistas.append(await service.sum_not_voided(sesion, evento.membership_id))

    events.subscribe(PaymentRegistered, sumar)
    await registrar(session, ACTOR, **_pago(membresia, amount_cop=30_000))
    assert vistas == [50_000]


async def test_auditoria_insert_con_el_socio_y_sin_confirmaciones(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    salida = await registrar(session, ACTOR, **_pago(membresia), confirm_duplicate=True)
    filas = await leer_auditoria_de_pagos(session, salida.id)
    assert [(f["action"], f["subject_member_id"], f["user_id"]) for f in filas] == [
        ("insert", membresia.member_id, ACTOR)
    ]
    despues = filas[0]["after"]
    assert despues["amount_cop"] == 60_000 and despues["method"] == "nequi"
    assert not [clave for clave in despues if clave.startswith("confirm")]


# Sumas (contrato para memberships, D11 y B7) -----------------------------------------------------


async def test_sum_not_voided_suma_solo_los_vigentes(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=30_000)
    await make_payment(session, membresia, amount=20_000, voided=True)
    await make_payment(session, membresia, amount=10_000, method="breb")
    total = await service.sum_not_voided(session, membresia.id)
    assert total == 40_000 and type(total) is int
    assert await service.sum_not_voided(session, uuid4()) == 0


async def test_sums_not_voided_por_lote_con_cero_para_las_que_no_tienen(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    primera = await _membresia(session)
    socio = await make_member(session, document=unique_document(), phone=None, email=None)
    plan = await make_plan(session, name="Trimestral", duration_days=90, price_cop=300_000)
    segunda = await make_membership(session, socio, plan)
    await make_payment(session, primera, amount=30_000)
    await make_payment(session, primera, amount=5_000, voided=True)
    await make_payment(session, segunda, amount=7_000, voided=True)
    sin_pagos = uuid4()
    sumas = await service.sums_not_voided(session, [primera.id, segunda.id, sin_pagos])
    assert sumas == {primera.id: 30_000, segunda.id: 0, sin_pagos: 0}


@pytest.fixture
def sentencias(engine: AsyncEngine) -> Iterator[list[str]]:
    vistas: list[str] = []

    def capturar(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        vistas.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capturar)
    try:
        yield vistas
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capturar)


async def test_sums_not_voided_consulta_por_lotes_y_sin_ids_no_consulta(
    session: AsyncSession, sentencias: list[str]
) -> None:
    assert await service.sums_not_voided(session, []) == {}
    assert [s for s in sentencias if "payments.payments" in s] == []
    ids = [uuid4() for _ in range(ID_BATCH * 2 + 50)]  # 450 ids: tres lotes
    sumas = await service.sums_not_voided(session, ids)
    assert sumas == dict.fromkeys(ids, 0)
    assert len([s for s in sentencias if "payments.payments" in s]) == 3


# Sobrepago (H-1, S3-D41) -------------------------------------------------------------------------


async def test_un_pago_igual_al_saldo_pasa(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=60_000)
    await registrar(session, ACTOR, **_pago(membresia, amount_cop=60_000))
    assert await service.sum_not_voided(session, membresia.id) == 120_000


async def test_un_peso_sobre_el_saldo_es_409_y_con_confirmacion_se_registra(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=60_000)
    with pytest.raises(PaymentExceedsBalance) as error:
        await registrar(session, ACTOR, **_pago(membresia, amount_cop=60_001))
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "payment_exceeds_balance",
        "amount_cop",
    )
    assert len(await pagos_de(session, membresia.id)) == 1
    salida = await registrar(
        session, ACTOR, **_pago(membresia, amount_cop=60_001), confirm_overpayment=True
    )
    assert salida.amount_cop == 60_001
    assert await service.sum_not_voided(session, membresia.id) == 120_001


async def test_un_pago_anulado_no_cuenta_para_el_saldo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await make_payment(session, membresia, amount=120_000, voided=True)
    await registrar(session, ACTOR, **_pago(membresia, amount_cop=120_000))


# Duplicado (H-1, S3-D41) -------------------------------------------------------------------------


async def test_dos_registros_iguales_seguidos_el_segundo_es_409(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference="REC-1")
    await registrar(session, ACTOR, **datos)
    with pytest.raises(PossibleDuplicatePayment) as error:
        await registrar(session, ACTOR, **datos)
    assert (error.value.status, error.value.code) == (409, "payment_possible_duplicate")
    assert len(await pagos_de(session, membresia.id)) == 1
    await registrar(session, ACTOR, **datos, confirm_duplicate=True)
    assert len(await pagos_de(session, membresia.id)) == 2


@pytest.mark.parametrize(
    "cambio",
    [{"reference": "REC-2"}, {"method": "nequi"}, {"amount_cop": 30_001}],
    ids=["otra-referencia", "otro-medio", "otro-monto"],
)
async def test_un_pago_distinto_no_es_duplicado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, cambio: dict[str, Any]
) -> None:
    membresia = await _membresia(session)
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference="REC-1")
    await registrar(session, ACTOR, **datos)
    await registrar(session, ACTOR, **{**datos, **cambio})
    assert len(await pagos_de(session, membresia.id)) == 2


async def test_el_mismo_pago_de_otro_usuario_no_es_duplicado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference=None)
    await registrar(session, ACTOR, **datos)
    await registrar(session, OTRO_ACTOR, **datos)
    assert len(await pagos_de(session, membresia.id)) == 2


async def test_dos_pagos_sin_referencia_iguales_son_duplicado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference=None)
    await registrar(session, ACTOR, **datos)
    with pytest.raises(PossibleDuplicatePayment):
        await registrar(session, ACTOR, **datos)


async def test_tras_anular_el_primero_el_mismo_pago_no_es_duplicado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    await make_payment(
        session,
        membresia,
        amount=30_000,
        method="cash",
        reference="REC-1",
        registered_by=ACTOR,
        voided=True,
    )
    await registrar(
        session, ACTOR, **_pago(membresia, amount_cop=30_000, method="cash", reference="REC-1")
    )
    assert len(await pagos_de(session, membresia.id)) == 2


@pytest.mark.parametrize(
    ("hace", "duplicado"),
    [(timedelta(seconds=119), True), (timedelta(seconds=121), False)],
    ids=["119-s", "121-s"],
)
async def test_la_ventana_de_duplicado_es_de_120_segundos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, hace: timedelta, duplicado: bool
) -> None:
    membresia = await _membresia(session)
    await make_payment(
        session,
        membresia,
        amount=30_000,
        method="cash",
        reference="REC-1",
        registered_by=ACTOR,
        created_at=T0 - hace,
    )
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference="REC-1")
    if duplicado:
        with pytest.raises(PossibleDuplicatePayment):
            await registrar(session, ACTOR, **datos)
        assert len(await pagos_de(session, membresia.id)) == 1
    else:
        await registrar(session, ACTOR, **datos)
        assert len(await pagos_de(session, membresia.id)) == 2


async def _intentar(sesion: AsyncSession, datos: dict[str, Any]) -> object:
    with actor_scope(ACTOR):
        try:
            salida = await service.register(sesion, **datos, role="coach")
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_pagos_identicos_simultaneos_el_candado_los_serializa(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    gate_doble: GateDoble,
) -> None:
    """El `FOR UPDATE` del gate sobre la fila de la membresía serializa los dos pagos: el segundo
    ve el primero confirmado y responde `payment_possible_duplicate`."""
    primera, segunda = dos_sesiones
    membresia = await _membresia(primera)
    datos = _pago(membresia, amount_cop=30_000, method="cash", reference="REC-1")
    resultados = await asyncio.gather(_intentar(primera, datos), _intentar(segunda, datos))
    duplicados = [r for r in resultados if isinstance(r, PossibleDuplicatePayment)]
    registrados = [r for r in resultados if not isinstance(r, DomainError)]
    assert len(duplicados) == 1 and len(registrados) == 1, resultados
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        assert len(await pagos_de(lectora, membresia.id)) == 1
    assert sorted(gate_doble.llamadas) == [membresia.id, membresia.id]


# Tope de pagos por membresía (H-2, S3-D42) -------------------------------------------------------


async def _con_pagos(session: AsyncSession, vigentes: int, anulados: int = 0) -> Membership:
    membresia = await _membresia(session, price=1_000_000)
    for _ in range(vigentes):
        await make_payment(session, membresia, amount=1_000)
    for _ in range(anulados):
        await make_payment(session, membresia, amount=1_000, voided=True)
    return membresia


async def test_el_pago_61_no_anulado_es_payment_limit_reached(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _con_pagos(session, vigentes=60)
    with pytest.raises(PaymentLimitReached) as error:
        await registrar(session, ACTOR, **_pago(membresia, amount_cop=1_000, reference=None))
    assert (error.value.status, error.value.code) == (409, "payment_limit_reached")
    assert len(await pagos_de(session, membresia.id)) == 60


async def test_un_pago_anulado_no_cuenta_para_el_tope(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _con_pagos(session, vigentes=59, anulados=1)
    await registrar(session, ACTOR, **_pago(membresia, amount_cop=1_000, reference=None))
    assert len(await pagos_de(session, membresia.id)) == 61


# paid_at por rol (M-4, M-8, S3-D51) --------------------------------------------------------------


async def test_el_coach_no_registra_8_dias_atras_y_el_admin_si(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    hace_ocho = T0 - timedelta(days=8)  # 2026-10-13T15:00:00Z
    with pytest.raises(PaidAtTooRetroactive) as error:
        await registrar(session, ACTOR, **_pago(membresia, paid_at=hace_ocho), role="coach")
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "paid_at_too_retroactive",
        "paid_at",
    )
    assert await pagos_de(session, membresia.id) == []
    salida = await registrar(session, ACTOR, **_pago(membresia, paid_at=hace_ocho), role="admin")
    assert salida.paid_at == hace_ocho


async def test_el_tope_del_coach_sale_de_la_politica_guardada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    politica = {
        "expiring_days": 7,
        "max_freeze_days_per_membership": 30,
        "max_freezes_per_membership": 2,
        "max_retroactive_days": 3,
    }
    with actor_scope(ACTOR):
        await settings_service.update_section(session, SectionKey.memberships, politica, 0, ACTOR)
    membresia = await _membresia(session)
    with pytest.raises(PaidAtTooRetroactive):
        await registrar(session, ACTOR, **_pago(membresia, paid_at=T0 - timedelta(days=4, hours=1)))
    await registrar(session, ACTOR, **_pago(membresia, paid_at=T0 - timedelta(days=3)))


async def test_paid_at_mas_alla_de_la_tolerancia_es_422_sin_fila(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _membresia(session)
    with pytest.raises(PaidAtInFuture) as error:
        await registrar(
            session, ACTOR, **_pago(membresia, paid_at=T0 + timedelta(minutes=5, seconds=1))
        )
    assert (error.value.status, error.value.field) == (422, "paid_at")
    assert await pagos_de(session, membresia.id) == []
