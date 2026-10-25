"""`memberships.service.sell` (S3-B1, US-084; blueprint B1 "Rojo"; D3, D8, D15, D16, N-24, M-4).

"Hoy" es 2026-10-21 (`reloj`, D33). Fechas a mano (N-23, fin inclusivo `start + duration_days`):
plan "Mensual" de 30 días vendido hoy termina el 2026-11-20; la "Tiquetera 12" de 60 días el
2026-12-20 (21 oct + 10 = 31 oct, + 30 = 30 nov, + 20 = 20 dic); empezando el 2026-10-31 termina
el 2026-11-30. `max_retroactive_days` por defecto es 7 (hoy - 7 = 2026-10-14 se acepta, hoy - 8 =
2026-10-13 no). `MAX_START_AHEAD_DAYS = 366` (hoy + 366 = 2027-10-22 se acepta, hoy + 367 =
2027-10-23 no).

Casos: venta por días y tiquetera con el precio copiado del plan (cambiarlo después no cambia
`agreed_price_cop`); 404 del socio, 422 del socio dado de baja o inactivo, del plan inexistente,
dado de baja o inactivo; 409 `membership_conflict` con `existing_id` (vigente o solo futura
pendiente); 409 `membership_overlap` con una vencida que se cruza; la `EXCLUDE` por SQL crudo
(23P01 con `constraint_name`) y su traducción en `sell`; venta tras `expired` o `cancelled`;
retroactividad y `enforce_retroactive_limit=False`; una fila `insert` de auditoría con
`subject_member_id`; `MembershipSold` una vez; un handler que falla no deja nada (savepoint de
D3); dos ventas simultáneas del mismo socio con `dos_sesiones`: una gana y la otra recibe 409.
`renew=True` sigue en `NotImplementedError` hasta B6; la venta con `first_payment` (B4) se prueba
en `test_sell_with_payment_service.py`.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import violated_constraint
from app.core.errors import DomainError
from app.modules.members.exceptions import MemberNotFound
from app.modules.memberships import sell as sell_module
from app.modules.memberships import service
from app.modules.memberships.exceptions import (
    MemberInactive,
    MembershipConflict,
    MembershipOverlap,
    PlanInactive,
    PlanInvalid,
    StartDateTooFar,
    StartDateTooRetroactive,
)
from app.modules.memberships.models import EXCLUDE_NAME
from app.modules.memberships.service import MembershipSold
from tests.conftest import CapturarEventos
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import leer_auditoria, leer_membresia, membresias_del_socio, vender

ACTOR = UUID("0000000a-0000-4000-8000-00000000a001")
HOY = date(2026, 10, 21)
TABLA = "memberships.memberships"
EXCLUSION_VIOLATION = "23P01"


async def _contar_auditoria_del_socio(session: AsyncSession, member_id: UUID) -> int:
    consulta = text(
        "SELECT count(*) FROM audit.audit_log WHERE table_name = :t AND subject_member_id = :m"
    )
    return int(await session.scalar(consulta, {"t": TABLA, "m": member_id}) or 0)


# Venta feliz ------------------------------------------------------------------------------------


async def test_vender_por_dias_sin_fecha_empieza_hoy_y_queda_pendiente_de_pago(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert salida.status == "pending_payment"
    assert (salida.start_date, salida.end_date) == (HOY, date(2026, 11, 20))
    assert salida.agreed_price_cop == 120_000 and type(salida.agreed_price_cop) is int
    assert salida.paid_cop == 0
    assert (salida.classes_total, salida.classes_remaining) == (None, None)
    assert (salida.member_id, salida.plan_id) == (socio.id, plan.id)
    assert (salida.member_name, salida.plan_name) == ("Lucía Gómez", "Mensual")
    assert salida.freezes == []
    assert (salida.first_payment_id, salida.cancel_reason, salida.cancelled_at) == (
        None,
        None,
        None,
    )
    fila = await leer_membresia(session, salida.id)
    assert fila is not None
    assert fila["status"] == "pending_payment"
    assert (fila["start_date"], fila["end_date"]) == (HOY, date(2026, 11, 20))
    assert fila["agreed_price_cop"] == 120_000
    assert fila["created_by"] == ACTOR


async def test_vender_una_tiquetera_copia_las_clases(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(
        session,
        name="Tiquetera 12",
        kind="classes",
        class_count=12,
        duration_days=60,
        price_cop=200_000,
    )
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert (salida.classes_total, salida.classes_remaining) == (12, 12)
    assert salida.end_date == date(2026, 12, 20)
    assert salida.agreed_price_cop == 200_000
    fila = await leer_membresia(session, salida.id)
    assert fila is not None and (fila["classes_total"], fila["classes_remaining"]) == (12, 12)


async def test_vender_con_fecha_de_inicio_futura(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(
        session, ACTOR, member_id=socio.id, plan_id=plan.id, start_date=date(2026, 10, 31)
    )
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 31), date(2026, 11, 30))
    assert salida.status == "pending_payment"


async def test_cambiar_el_precio_del_plan_despues_no_cambia_el_pactado(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    await session.execute(
        text("UPDATE plans.plans SET price_cop = 150000 WHERE id = :id"), {"id": plan.id}
    )
    fila = await leer_membresia(session, salida.id)
    assert fila is not None and fila["agreed_price_cop"] == 120_000


# Socio y plan --------------------------------------------------------------------------------


async def test_socio_inexistente_es_member_not_found(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    with pytest.raises(MemberNotFound) as error:
        await vender(session, ACTOR, member_id=uuid4(), plan_id=plan.id)
    assert (error.value.status, error.value.code) == (404, "member_not_found")


@pytest.mark.parametrize("cambios", ["baja", "inactivo"])
async def test_socio_dado_de_baja_o_inactivo_es_member_inactive(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, cambios: str
) -> None:
    extra: dict[str, Any] = (
        {"deleted_at": reloj.now_utc()} if cambios == "baja" else {"status": "inactive"}
    )
    socio = await make_member(session, **extra)
    plan = await make_plan(session)
    with pytest.raises(MemberInactive) as error:
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert (error.value.status, error.value.code) == (422, "member_inactive")
    assert await membresias_del_socio(session, socio.id) == []


async def test_plan_inexistente_o_dado_de_baja_es_plan_invalid(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    baja = await make_plan(session, name="Viejo", deleted_at=reloj.now_utc())
    for plan_id in (uuid4(), baja.id):
        with pytest.raises(PlanInvalid) as error:
            await vender(session, ACTOR, member_id=socio.id, plan_id=plan_id)
        assert (error.value.status, error.value.code, error.value.field) == (
            422,
            "plan_invalid",
            "plan_id",
        )
    assert await membresias_del_socio(session, socio.id) == []


async def test_plan_inactivo_es_plan_inactive(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session, is_active=False)
    with pytest.raises(PlanInactive) as error:
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "plan_inactive",
        "plan_id",
    )


# Conflictos y solapes (D8) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "inicio"),
    [
        ("active", date(2026, 10, 1)),
        ("frozen", date(2026, 10, 1)),
        ("pending_payment", date(2026, 11, 25)),
        ("active", date(2026, 11, 25)),
    ],
    ids=["vigente", "vigente-congelada", "solo-futura-pendiente", "futura-activa"],
)
async def test_con_vigente_o_futura_es_membership_conflict_con_existing_id(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, estado: str, inicio: date
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    previa = await make_membership(session, socio, plan, status=estado, start=inicio)
    with pytest.raises(MembershipConflict) as error:
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert (error.value.status, error.value.code) == (409, "membership_conflict")
    assert error.value.existing_id == previa.id
    assert len(await membresias_del_socio(session, socio.id)) == 1


async def test_fechas_que_chocan_con_una_vencida_son_membership_overlap(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Guardada `active` pero vencida por fecha (18 sep a 18 oct): no es vigente (D5), pero sus
    fechas chocan con una venta que empieza el 15 de octubre (hoy - 6)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    vieja = await make_membership(session, socio, plan, status="active", start=date(2026, 9, 18))
    with pytest.raises(MembershipOverlap) as error:
        await vender(
            session, ACTOR, member_id=socio.id, plan_id=plan.id, start_date=date(2026, 10, 15)
        )
    assert (error.value.status, error.value.code) == (409, "membership_overlap")
    assert error.value.existing_id == vieja.id


async def test_la_exclude_rechaza_dos_rangos_solapados_por_sql_crudo(
    session: AsyncSession, reloj: FrozenClock
) -> None:
    """La exploración pide comprobar que `constraint_name` llega en la causa de asyncpg."""
    socio = uuid4()
    insertar = text(
        "INSERT INTO memberships.memberships (id, created_by, member_id, plan_id, "
        "agreed_price_cop, start_date, end_date, status) "
        "VALUES (:id, :actor, :m, :p, 120000, :s, :e, 'active')"
    )
    base = {"actor": ACTOR, "m": socio, "p": uuid4()}
    await session.execute(
        insertar, {**base, "id": uuid4(), "s": date(2026, 10, 1), "e": date(2026, 10, 28)}
    )
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(
                insertar, {**base, "id": uuid4(), "s": date(2026, 10, 28), "e": date(2026, 11, 27)}
            )
    assert violated_constraint(error.value) == EXCLUDE_NAME
    assert getattr(error.value.orig, "sqlstate", None) == EXCLUSION_VIOLATION


async def test_sell_traduce_la_exclude_a_membership_overlap(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La `EXCLUDE` es la red ante la carrera (D8): sin la revisión previa en código, el flush
    choca con 23P01 y `sell` responde `MembershipOverlap` (sin `existing_id`: la base no lo da)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(session, socio, plan, status="active", start=date(2026, 10, 1))

    async def sin_revision(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(sell_module, "_check_open_memberships", sin_revision)
    with pytest.raises(MembershipOverlap) as error:
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert error.value.code == "membership_overlap"
    assert len(await membresias_del_socio(session, socio.id)) == 1


@pytest.mark.parametrize(
    ("estado", "inicio"),
    [("expired", date(2026, 9, 1)), ("cancelled", date(2026, 10, 1))],
    ids=["tras-vencida", "tras-cancelada"],
)
async def test_se_vende_tras_una_vencida_o_cancelada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, estado: str, inicio: date
) -> None:
    """La vencida (1 sep a 1 oct) no choca con hoy; la cancelada (1 a 31 oct) la ignora la
    `EXCLUDE` (`WHERE status <> 'cancelled'`)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(session, socio, plan, status=estado, start=inicio)
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert salida.status == "pending_payment"
    assert len(await membresias_del_socio(session, socio.id)) == 2


# Fechas de inicio (N-24, M-4) -------------------------------------------------------------------


async def test_hoy_menos_7_se_acepta_y_hoy_menos_8_no(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    primero = await make_member(session, document=unique_document())
    segundo = await make_member(session, document=unique_document(), phone=None, email=None)
    plan = await make_plan(session)
    salida = await vender(
        session, ACTOR, member_id=primero.id, plan_id=plan.id, start_date=date(2026, 10, 14)
    )
    assert (salida.start_date, salida.end_date) == (date(2026, 10, 14), date(2026, 11, 13))
    with pytest.raises(StartDateTooRetroactive) as error:
        await vender(
            session, ACTOR, member_id=segundo.id, plan_id=plan.id, start_date=date(2026, 10, 13)
        )
    assert (error.value.code, error.value.field) == ("start_date_too_retroactive", "start_date")
    assert await membresias_del_socio(session, segundo.id) == []


async def test_sin_tope_retroactivo_se_vende_con_fecha_antigua(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """`enforce_retroactive_limit=False` (importación, N-24; solo el CLI lo pasa, L-6)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(
        session,
        ACTOR,
        member_id=socio.id,
        plan_id=plan.id,
        start_date=date(2026, 1, 1),
        enforce_retroactive_limit=False,
    )
    assert (salida.start_date, salida.end_date) == (date(2026, 1, 1), date(2026, 1, 31))


async def test_hoy_mas_366_se_acepta_y_hoy_mas_367_es_start_date_too_far(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    primero = await make_member(session, document=unique_document())
    segundo = await make_member(session, document=unique_document(), phone=None, email=None)
    plan = await make_plan(session)
    salida = await vender(
        session, ACTOR, member_id=primero.id, plan_id=plan.id, start_date=date(2027, 10, 22)
    )
    assert salida.end_date == date(2027, 11, 21)
    for lejana in (date(2027, 10, 23), date(9999, 12, 31)):
        with pytest.raises(StartDateTooFar) as error:
            await vender(session, ACTOR, member_id=segundo.id, plan_id=plan.id, start_date=lejana)
        assert (error.value.status, error.value.code, error.value.field) == (
            422,
            "start_date_too_far",
            "start_date",
        )
    assert await membresias_del_socio(session, segundo.id) == []


# Auditoría, evento y atomicidad (D3) ---------------------------------------------------------


async def test_la_venta_deja_una_fila_insert_de_auditoria_con_el_socio(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    filas = await leer_auditoria(session, TABLA, salida.id)
    assert [(f["action"], f["subject_member_id"], f["user_id"]) for f in filas] == [
        ("insert", socio.id, ACTOR)
    ]


async def test_la_venta_emite_membership_sold_una_vez(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(MembershipSold)
    socio = await make_member(session)
    plan = await make_plan(session)
    salida = await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id)
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert (evento.membership_id, evento.member_id, evento.plan_id) == (
        salida.id,
        socio.id,
        plan.id,
    )
    assert evento.agreed_price_cop == 120_000
    assert (evento.start_date, evento.end_date) == (HOY, date(2026, 11, 20))
    assert evento.renewal is False


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_que_falla_no_deja_membresia_ni_auditoria(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)

    async def roto(evento: MembershipSold, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipSold, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ACTOR):
        await service.sell(session, member_id=socio.id, plan_id=plan.id)
    assert await membresias_del_socio(session, socio.id) == []
    assert await _contar_auditoria_del_socio(session, socio.id) == 0


async def test_renovar_sigue_sin_implementar_hasta_b6(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """B6 (`renew`) lo implementa; hasta entonces falla cerrado. `first_payment` llegó en B4
    (`test_sell_with_payment_service.py`)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    with pytest.raises(NotImplementedError):
        await vender(session, ACTOR, member_id=socio.id, plan_id=plan.id, renew=True)


# Concurrencia (D3, con commit real) ------------------------------------------------------------


async def _intentar(sesion: AsyncSession, member_id: UUID, plan_id: UUID) -> object:
    with actor_scope(ACTOR):
        try:
            salida = await service.sell(sesion, member_id=member_id, plan_id=plan_id)
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_ventas_simultaneas_del_mismo_socio_una_gana_y_la_otra_es_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    plan = await make_plan(primera)
    socio_id, plan_id = socio.id, plan.id
    resultados = await asyncio.gather(
        _intentar(primera, socio_id, plan_id), _intentar(segunda, socio_id, plan_id)
    )
    conflictos = [r for r in resultados if isinstance(r, MembershipConflict)]
    ganadoras = [r for r in resultados if not isinstance(r, DomainError)]
    assert len(conflictos) == 1 and len(ganadoras) == 1, resultados
    assert conflictos[0].existing_id == ganadoras[0].id  # type: ignore[attr-defined]
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        assert len(await membresias_del_socio(lectora, socio_id)) == 1
