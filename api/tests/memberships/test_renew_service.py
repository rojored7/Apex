"""Renovar una membresía (S3-B6, US-088; blueprint B6 y flujo 6.4; Q1, D3, D8, S3-D8, M-4).

`sell(..., renew=True)`: el `start_date` recibido se descarta; bajo el candado del socio, si hay
una futura (D8: `pending_payment` de cualquier fecha, o `active`/`expiring` con
`start_date > hoy`) es 409 `future_membership_exists` con `existing_id`; si no,
`rules.plan_renewal(vigente_o_None, plan, price_cop, hoy)` fija inicio, fin y precio; mismas
validaciones de socio y plan, mismo primer pago (D4) y `MembershipSold(renewal=True)`; ni
`start_date_too_far` (M-4) ni el límite retroactivo aplican. `renewal_preview(session, *,
member_id, plan_id)` devuelve lo mismo que crearía la renovación (`RenewalPreviewOut`), sin
escribir y sin candados (ni el del socio, ni `FOR SHARE` del plan, ni `FOR UPDATE`).

"Hoy" es 2026-10-21 (`reloj`, D33), `expiring_days = 7`. Fechas a mano (N-23: fin inclusivo
`inicio + duration_days`; Q1: la renovación empieza el día siguiente al fin de la vigente):
- vigente "Mensual" (120.000, 30 días) del 2026-09-28 al 2026-10-28 (efectiva `expiring`: faltan
  7 días): renovar da del 2026-10-29 al 2026-11-28 (29 oct + 2 = 31 oct, + 28 = 28 nov);
- vencida del 2026-09-01 al 2026-10-01: renovar empieza hoy, del 2026-10-21 al 2026-11-20;
- sin membresías, o solo canceladas: empieza hoy;
- "Trimestral" (300.000, 90 días) desde el 2026-10-29: 29 oct + 2 = 31 oct (2), + 30 = 30 nov
  (32), + 31 = 31 dic (63), + 27 = 27 ene (90): fin 2027-01-27;
- vigente del 2026-10-01 al 2026-10-31 congelada del 2026-10-21 al 2026-10-30 (10 días, RN-07):
  el fin pasa al 2026-11-10 y la renovación va del 2026-11-11 al 2026-12-11;
- vigente del 2026-10-21 al 2027-11-25 (fin lejano): la renovación empieza el 2027-11-26, más de
  366 días después de hoy (2027-10-22 es el tope de una venta sin `renew`), y termina el
  2027-12-26: `renew` no aplica `start_date_too_far`.
Adyacentes no se solapan (`daterange '[]'`): 28 y 29 de octubre conviven.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.errors import DomainError
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.models import Member
from app.modules.memberships import service
from app.modules.memberships.exceptions import (
    FutureMembershipExists,
    MemberInactive,
    PlanInactive,
    PlanInvalid,
)
from app.modules.memberships.models import Membership
from app.modules.memberships.rules import (
    MembershipSnapshot,
    MembershipStatus,
    PlanTerms,
    RenewalPlan,
    plan_renewal,
)
from app.modules.memberships.schemas import RenewalPreviewOut
from app.modules.memberships.service import MembershipSold
from app.modules.payments.exceptions import PaymentExceedsBalance
from app.modules.payments.schemas import PaymentIn
from app.modules.plans.models import Plan
from tests.conftest import CapturarEventos
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    congelar,
    leer_auditoria,
    leer_membresia,
    membresias_del_socio,
    vender,
)
from tests.payments._apoyo import pagos_de

ACTOR = UUID("0000000a-0000-4000-8000-00000000b601")
HOY = date(2026, 10, 21)
TABLA = "memberships.memberships"
MENSUAL = PlanTerms(kind="days", duration_days=30, class_count=None)


def _snap(status: MembershipStatus, inicio: date, fin: date) -> MembershipSnapshot:
    return MembershipSnapshot(
        id=uuid4(), status=status, start_date=inicio, end_date=fin, classes_remaining=None
    )


# Regla pura: plan_renewal (Q1) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "esperado"),
    [
        (
            _snap(MembershipStatus.expiring, date(2026, 9, 28), date(2026, 10, 28)),
            (date(2026, 10, 29), date(2026, 11, 28)),
        ),
        (
            _snap(MembershipStatus.active, date(2026, 10, 1), date(2026, 10, 21)),
            (date(2026, 10, 22), date(2026, 11, 21)),
        ),
        (
            _snap(MembershipStatus.frozen, date(2026, 10, 1), date(2026, 11, 10)),
            (date(2026, 11, 11), date(2026, 12, 11)),
        ),
        (
            _snap(MembershipStatus.expired, date(2026, 9, 1), date(2026, 10, 1)),
            (HOY, date(2026, 11, 20)),
        ),
        (None, (HOY, date(2026, 11, 20))),
    ],
    ids=["vigente-hasta-el-28", "vence-hoy", "congelada-extendida", "vencida", "sin-vigente"],
)
def test_plan_renewal_empieza_el_dia_siguiente_al_fin_de_la_vigente_o_hoy(
    actual: MembershipSnapshot | None, esperado: tuple[date, date]
) -> None:
    plan = plan_renewal(actual, MENSUAL, 120_000, HOY)
    assert plan == RenewalPlan(
        start_date=esperado[0], end_date=esperado[1], agreed_price_cop=120_000
    )


def test_plan_renewal_usa_la_duracion_y_el_precio_del_plan_nuevo() -> None:
    vigente = _snap(MembershipStatus.expiring, date(2026, 9, 28), date(2026, 10, 28))
    trimestral = PlanTerms(kind="days", duration_days=90, class_count=None)
    tiquetera = PlanTerms(kind="classes", duration_days=60, class_count=12)
    assert plan_renewal(vigente, trimestral, 300_000, HOY) == RenewalPlan(
        start_date=date(2026, 10, 29), end_date=date(2027, 1, 27), agreed_price_cop=300_000
    )
    assert plan_renewal(vigente, tiquetera, 99_000, HOY) == RenewalPlan(
        start_date=date(2026, 10, 29), end_date=date(2026, 12, 28), agreed_price_cop=99_000
    )


def test_plan_renewal_no_muta_la_vigente_y_es_inmutable() -> None:
    vigente = _snap(MembershipStatus.active, date(2026, 10, 1), date(2026, 10, 31))
    copia = MembershipSnapshot(
        id=vigente.id,
        status=vigente.status,
        start_date=vigente.start_date,
        end_date=vigente.end_date,
        classes_remaining=vigente.classes_remaining,
    )
    resultado = plan_renewal(vigente, MENSUAL, 120_000, HOY)
    assert vigente == copia
    with pytest.raises(FrozenInstanceError):
        resultado.start_date = HOY  # type: ignore[misc]


# Escenarios ------------------------------------------------------------------------------------


async def _socio_y_plan(session: AsyncSession, **plan: Any) -> tuple[UUID, Plan]:
    socio = await make_member(session)
    return socio.id, await make_plan(session, **plan)


async def _con_vigente(session: AsyncSession) -> tuple[UUID, Plan, Membership]:
    """Socio con una `active` del 2026-09-28 al 2026-10-28 (efectiva `expiring`)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(session, socio, plan, status="active", start=date(2026, 9, 28))
    assert vigente.end_date == date(2026, 10, 28)
    return socio.id, plan, vigente


async def _renovar(session: AsyncSession, member_id: UUID, plan_id: UUID, **datos: Any) -> Any:
    return await vender(session, ACTOR, member_id=member_id, plan_id=plan_id, renew=True, **datos)


async def _contar_auditoria_del_socio(session: AsyncSession, member_id: UUID) -> int:
    consulta = text(
        "SELECT count(*) FROM audit.audit_log WHERE table_name = :t AND subject_member_id = :m"
    )
    return int(await session.scalar(consulta, {"t": TABLA, "m": member_id}) or 0)


# Renovar ---------------------------------------------------------------------------------------


async def test_renovar_una_vigente_empieza_el_dia_siguiente_y_queda_pendiente_de_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, vigente = await _con_vigente(session)
    vigente_id, plan_id = vigente.id, plan.id
    antes = await leer_membresia(session, vigente_id)
    auditoria_antes = await leer_auditoria(session, TABLA, vigente_id)
    salida = await _renovar(session, socio_id, plan_id)
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 29), date(2026, 11, 28))
    assert salida.status == "pending_payment"
    assert (salida.agreed_price_cop, salida.paid_cop, salida.first_payment_id) == (120_000, 0, None)
    assert salida.id != vigente_id
    assert await leer_membresia(session, vigente_id) == antes
    assert await leer_auditoria(session, TABLA, vigente_id) == auditoria_antes
    nueva = await leer_auditoria(session, TABLA, salida.id)
    assert [(f["action"], f["subject_member_id"]) for f in nueva] == [("insert", socio_id)]
    filas = await membresias_del_socio(session, socio_id)
    assert [(f["start_date"], f["end_date"], f["status"]) for f in filas] == [
        (date(2026, 9, 28), date(2026, 10, 28), "active"),
        (date(2026, 10, 29), date(2026, 11, 28), "pending_payment"),
    ]


async def test_la_renovacion_y_la_vigente_son_adyacentes_y_no_se_solapan(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    await _renovar(session, socio_id, plan.id)
    consulta = text(
        "SELECT count(*) FROM memberships.memberships a JOIN memberships.memberships b "
        "ON a.member_id = b.member_id AND a.id < b.id "
        "WHERE a.member_id = :m AND a.status <> 'cancelled' AND b.status <> 'cancelled' "
        "AND daterange(a.start_date, a.end_date, '[]') && daterange(b.start_date, b.end_date, '[]')"
    )
    assert await session.scalar(consulta, {"m": socio_id}) == 0


@pytest.mark.parametrize("previa", ["vencida", "ninguna", "solo-cancelada"])
async def test_sin_vigente_la_renovacion_empieza_hoy(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, previa: str
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    if previa == "vencida":
        await make_membership(session, socio, plan, status="active", start=date(2026, 9, 1))
    elif previa == "solo-cancelada":
        await make_membership(session, socio, plan, status="cancelled", start=date(2026, 10, 15))
    salida = await _renovar(session, socio.id, plan.id)
    assert (salida.start_date, salida.end_date) == (HOY, date(2026, 11, 20))
    assert salida.status == "pending_payment"


async def test_renovar_con_pago_completo_deja_una_futura_activa(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, vigente = await _con_vigente(session)
    vigente_id = vigente.id
    salida = await _renovar(
        session,
        socio_id,
        plan.id,
        first_payment=PaymentIn(amount_cop=120_000, method="nequi", reference="NEQ-RENUEVA"),
        role="coach",
    )
    assert salida.status == "active"
    assert salida.start_date == date(2026, 10, 29) and salida.start_date > HOY
    assert salida.paid_cop == 120_000 and salida.first_payment_id is not None
    pagos = await pagos_de(session, salida.id)
    assert [(p["id"], p["amount_cop"]) for p in pagos] == [(salida.first_payment_id, 120_000)]
    vigente_fila = await leer_membresia(session, vigente_id)
    assert vigente_fila is not None and vigente_fila["status"] == "active"


async def test_el_primer_pago_mayor_al_precio_sin_confirmar_da_409_y_no_crea_nada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    with pytest.raises(PaymentExceedsBalance) as error:
        await _renovar(
            session,
            socio_id,
            plan.id,
            first_payment=PaymentIn(amount_cop=150_000, method="cash"),
            role="admin",
        )
    assert (error.value.status, error.value.code) == (409, "payment_exceeds_balance")
    assert error.value.field == "first_payment.amount_cop"
    assert len(await membresias_del_socio(session, socio_id)) == 1


async def _futura_pendiente(session: AsyncSession) -> tuple[UUID, Plan, UUID]:
    socio_id, plan, _vigente = await _con_vigente(session)
    futura = await _insertar(session, socio_id, plan, "pending_payment", date(2026, 10, 29))
    return socio_id, plan, futura


async def _futura_activa(session: AsyncSession) -> tuple[UUID, Plan, UUID]:
    socio_id, plan, _vigente = await _con_vigente(session)
    futura = await _insertar(session, socio_id, plan, "active", date(2026, 10, 29))
    return socio_id, plan, futura


async def _solo_pendiente_de_hoy(session: AsyncSession) -> tuple[UUID, Plan, UUID]:
    socio_id, plan = await _socio_y_plan(session)
    futura = await _insertar(session, socio_id, plan, "pending_payment", HOY)
    return socio_id, plan, futura


async def _insertar(
    session: AsyncSession, member_id: UUID, plan: Plan, status: str, inicio: date
) -> UUID:
    socio = await session.get_one(Member, member_id)
    membresia = await make_membership(session, socio, plan, status=status, start=inicio)
    return membresia.id


@pytest.mark.parametrize(
    "preparar",
    [_futura_pendiente, _futura_activa, _solo_pendiente_de_hoy],
    ids=["futura-pendiente", "futura-activa", "pendiente-de-hoy"],
)
async def test_si_ya_hay_una_futura_es_409_future_membership_exists_con_existing_id(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, preparar: Any
) -> None:
    socio_id, plan, futura_id = await preparar(session)
    plan_id = plan.id
    cuantas = len(await membresias_del_socio(session, socio_id))
    with pytest.raises(FutureMembershipExists) as error:
        await _renovar(session, socio_id, plan_id)
    assert (error.value.status, error.value.code) == (409, "future_membership_exists")
    assert error.value.existing_id == futura_id
    assert len(await membresias_del_socio(session, socio_id)) == cuantas


@pytest.mark.parametrize(
    "enviado", [date(2026, 12, 1), date(2026, 9, 1)], ids=["futuro", "retroactivo-de-30-dias"]
)
async def test_el_start_date_enviado_se_ignora(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, enviado: date
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    salida = await _renovar(session, socio_id, plan.id, start_date=enviado)
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 29), date(2026, 11, 28))


async def test_una_vencida_con_start_date_retroactivo_renueva_desde_hoy_sin_limite_retroactivo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(session, socio, plan, status="active", start=date(2026, 9, 1))
    salida = await _renovar(session, socio.id, plan.id, start_date=date(2026, 9, 21))
    assert (salida.start_date, salida.end_date) == (HOY, date(2026, 11, 20))


async def test_renew_no_aplica_start_date_too_far(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(session, socio, plan, status="active", start=HOY, end=date(2027, 11, 25))
    salida = await _renovar(session, socio.id, plan.id)
    assert (salida.start_date, salida.end_date) == (date(2027, 11, 26), date(2027, 12, 26))


async def test_renovar_con_otro_plan_usa_su_precio_y_su_duracion(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, _plan, _vigente = await _con_vigente(session)
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    salida = await _renovar(session, socio_id, trimestral.id)
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 29), date(2027, 1, 27))
    assert (salida.plan_id, salida.plan_name, salida.agreed_price_cop) == (
        trimestral.id,
        "Trimestral",
        300_000,
    )


@pytest.mark.parametrize("caso", ["inactivo", "inexistente", "dado-de-baja"])
async def test_un_plan_inactivo_inexistente_o_dado_de_baja_no_renueva(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, caso: str
) -> None:
    socio_id, _plan, _vigente = await _con_vigente(session)
    if caso == "inactivo":
        plan_id = (await make_plan(session, name="Viejo", is_active=False)).id
    elif caso == "dado-de-baja":
        plan_id = (await make_plan(session, name="Borrado", deleted_at=reloj.now_utc())).id
    else:
        plan_id = uuid4()
    esperado = PlanInactive if caso == "inactivo" else PlanInvalid
    with pytest.raises(esperado) as error:
        await _renovar(session, socio_id, plan_id)
    assert (error.value.status, error.value.field) == (422, "plan_id")
    assert len(await membresias_del_socio(session, socio_id)) == 1


@pytest.mark.parametrize("caso", ["baja", "inactivo"])
async def test_un_socio_dado_de_baja_o_inactivo_no_renueva(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, caso: str
) -> None:
    cambios = {"deleted_at": reloj.now_utc()} if caso == "baja" else {"status": "inactive"}
    socio = await make_member(session, **cambios)
    plan = await make_plan(session)
    with pytest.raises(MemberInactive):
        await _renovar(session, socio.id, plan.id)


async def test_un_socio_inexistente_da_member_not_found(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    with pytest.raises(MemberNotFound):
        await _renovar(session, uuid4(), plan.id)


async def test_una_vigente_congelada_renueva_desde_su_fin_ya_extendido(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(session, socio, plan, status="active", start=date(2026, 10, 1))
    assert vigente.end_date == date(2026, 10, 31)
    congelada = await congelar(
        session,
        ACTOR,
        membership_id=vigente.id,
        frozen_from=date(2026, 10, 21),
        frozen_to=date(2026, 10, 30),
    )
    assert (congelada.status, congelada.end_date) == ("frozen", date(2026, 11, 10))
    vista = await service.renewal_preview(session, member_id=socio.id, plan_id=plan.id)
    assert vista.current_end_date == date(2026, 11, 10)
    salida = await _renovar(session, socio.id, plan.id)
    assert (salida.start_date, salida.end_date) == (date(2026, 11, 11), date(2026, 12, 11))


async def test_una_cancelada_entre_las_dos_no_impide_renovar(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    cancelada = await _insertar(session, socio_id, plan, "cancelled", date(2026, 10, 29))
    salida = await _renovar(session, socio_id, plan.id)
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 29), date(2026, 11, 28))
    assert salida.id != cancelada
    estados = sorted(f["status"] for f in await membresias_del_socio(session, socio_id))
    assert estados == ["active", "cancelled", "pending_payment"]


async def test_renovar_emite_membership_sold_con_renewal_verdadero_una_vez(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    recibidos = capturar_eventos(MembershipSold)
    salida = await _renovar(session, socio_id, plan.id)
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert evento.renewal is True
    assert (evento.membership_id, evento.member_id) == (salida.id, socio_id)
    assert (evento.start_date, evento.end_date) == (date(2026, 10, 29), date(2026, 11, 28))
    assert evento.agreed_price_cop == 120_000


class _HandlerRoto(Exception):
    """Excepción propia (no `RuntimeError`: `NotImplementedError` lo es)."""


async def test_un_handler_que_falla_no_deja_la_renovacion(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)

    async def roto(evento: MembershipSold, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipSold, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ACTOR):
        await service.sell(session, member_id=socio_id, plan_id=plan.id, renew=True)
    assert len(await membresias_del_socio(session, socio_id)) == 1
    assert await _contar_auditoria_del_socio(session, socio_id) == 1  # solo el de la fábrica


# Vista previa ---------------------------------------------------------------------------------


@pytest.fixture
def sentencias(session: AsyncSession) -> Iterator[list[str]]:
    """Las sentencias que la conexión de `session` envía, en orden."""
    conexion = session.bind.sync_connection  # type: ignore[union-attr]
    vistas: list[str] = []

    def espiar(_c: object, _cur: object, sql: str, *_args: object) -> None:
        vistas.append(sql)

    event.listen(conexion, "before_cursor_execute", espiar)
    try:
        yield vistas
    finally:
        event.remove(conexion, "before_cursor_execute", espiar)


async def test_la_vista_previa_es_igual_a_lo_que_crea_la_renovacion_y_no_escribe(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    auditoria = await _contar_auditoria_del_socio(session, socio_id)
    vista = await service.renewal_preview(session, member_id=socio_id, plan_id=plan.id)
    assert vista == RenewalPreviewOut(
        start_date=date(2026, 10, 29),
        end_date=date(2026, 11, 28),
        agreed_price_cop=120_000,
        current_end_date=date(2026, 10, 28),
    )
    assert len(await membresias_del_socio(session, socio_id)) == 1
    assert await _contar_auditoria_del_socio(session, socio_id) == auditoria
    salida = await _renovar(session, socio_id, plan.id)
    assert (salida.start_date, salida.end_date, salida.agreed_price_cop) == (
        vista.start_date,
        vista.end_date,
        vista.agreed_price_cop,
    )


async def test_la_vista_previa_no_toma_candados_ni_escribe(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, sentencias: list[str]
) -> None:
    socio_id, plan, _vigente = await _con_vigente(session)
    sentencias.clear()
    await service.renewal_preview(session, member_id=socio_id, plan_id=plan.id)
    assert sentencias, "la vista previa debe leer la base"
    prohibidas = [
        s
        for s in sentencias
        if "FOR UPDATE" in s.upper()
        or "FOR SHARE" in s.upper()
        or "PG_ADVISORY" in s.upper()
        or s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert prohibidas == [], prohibidas


async def test_la_vista_previa_sin_vigente_empieza_hoy_y_no_tiene_fin_actual(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan = await _socio_y_plan(
        session, name="Trimestral", price_cop=300_000, duration_days=90
    )
    vista = await service.renewal_preview(session, member_id=socio_id, plan_id=plan.id)
    assert vista == RenewalPreviewOut(
        start_date=HOY,
        end_date=date(2027, 1, 19),
        agreed_price_cop=300_000,
        current_end_date=None,
    )


async def test_la_vista_previa_comparte_las_validaciones(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio_id, plan, futura_id = await _futura_pendiente(session)
    with pytest.raises(FutureMembershipExists) as conflicto:
        await service.renewal_preview(session, member_id=socio_id, plan_id=plan.id)
    assert conflicto.value.existing_id == futura_id
    inactivo = await make_plan(session, name="Viejo", is_active=False)
    with pytest.raises(PlanInactive):
        await service.renewal_preview(session, member_id=socio_id, plan_id=inactivo.id)
    with pytest.raises(PlanInvalid):
        await service.renewal_preview(session, member_id=socio_id, plan_id=uuid4())
    with pytest.raises(MemberNotFound):
        await service.renewal_preview(session, member_id=uuid4(), plan_id=plan.id)
    baja = await make_member(session, status="inactive", document=unique_document())
    with pytest.raises(MemberInactive):
        await service.renewal_preview(session, member_id=baja.id, plan_id=plan.id)


# Concurrencia (D3, con commit real) ------------------------------------------------------------


async def _intentar(sesion: AsyncSession, member_id: UUID, plan_id: UUID) -> object:
    with actor_scope(ACTOR):
        try:
            salida = await service.sell(sesion, member_id=member_id, plan_id=plan_id, renew=True)
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_renovaciones_a_la_vez_una_gana_y_la_otra_es_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    socio_id, plan, _vigente = await _con_vigente(primera)
    plan_id = plan.id
    resultados = await asyncio.gather(
        _intentar(primera, socio_id, plan_id), _intentar(segunda, socio_id, plan_id)
    )
    conflictos = [r for r in resultados if isinstance(r, FutureMembershipExists)]
    ganadoras = [r for r in resultados if not isinstance(r, DomainError)]
    assert len(conflictos) == 1 and len(ganadoras) == 1, resultados
    assert conflictos[0].existing_id == ganadoras[0].id  # type: ignore[attr-defined]
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        assert len(await membresias_del_socio(lectora, socio_id)) == 2
