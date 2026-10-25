"""`memberships.service.freeze` (S3-B2, US-089; blueprint B2 "Rojo"; D3, D14, Q9, RN-07, N-25).

"Hoy" es 2026-10-21 (`reloj`). La membresía base es `active` del 2026-10-01 al 2026-10-31 (plan
"Mensual" de 30 días: 1 oct + 30 = 31 oct); hoy faltan 10 días, así que es `active` con
`expiring_days = 7`. Fechas a mano (RN-07, el fin se corre `(frozen_to - frozen_from) + 1` días):
- congelar del 21 al 30 de octubre (10 días) deja `frozen` y el fin en el 2026-11-10;
- congelar del 25 al 27 de octubre (3 días, futura) deja `active` y el fin en el 2026-11-03;
- una futura que empieza el 2026-11-01 choca con el fin corrido (409
  `overlaps_future_membership`); una que empieza el 2026-11-11 queda contigua y no choca;
- por defecto (sin sección guardada) el tope es 30 días: del 21 de octubre al 20 de noviembre son
  31 y se rechazan; con `max_freeze_days_per_membership = 40` guardado entran (fin 2026-12-01);
- segunda y tercera: del 21 al 22 (2 días, fin 2 nov); el 25 la primera ya terminó y se congela el
  25 y 26 (fin 4 nov); el 28 la tercera es 409 `freeze_limit_reached`.

También: 404 `membership_not_found`; los `FreezeError` de la regla salen como `FreezeRejected`
con su `code`, `field` y `status`; auditoría `insert` en `membership_freezes` y `update` en
`memberships` (solo `end_date` y `status`, con `subject_member_id`); `MembershipFrozen` una vez;
un handler que falla no deja nada (savepoint, regla transversal 5); la `EXCLUDE` de congelaciones
por SQL crudo (23P01) y la de membresías traducida a `OverlapsFutureMembership`; el candado del
socio antes del `FOR UPDATE` (D3); dos congelaciones simultáneas con `dos_sesiones`: una gana.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import violated_constraint
from app.core.errors import DomainError
from app.modules.memberships import lifecycle as lifecycle_module
from app.modules.memberships import service
from app.modules.memberships.exceptions import (
    FreezeRejected,
    MembershipNotFound,
    OverlapsFutureMembership,
)
from app.modules.memberships.models import FREEZE_EXCLUDE_NAME, Membership
from app.modules.memberships.service import MembershipFrozen
from app.modules.settings.service import update_section
from tests.conftest import CapturarEventos
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    congelaciones_de,
    congelar,
    leer_auditoria,
    leer_membresia,
    membresias_del_socio,
)

ACTOR = UUID("0000000a-0000-4000-8000-00000000a003")
HOY = date(2026, 10, 21)
INICIO = date(2026, 10, 1)
FIN = date(2026, 10, 31)
TABLA_CONGELACIONES = "memberships.membership_freezes"
TABLA_MEMBRESIAS = "memberships.memberships"
EXCLUSION_VIOLATION = "23P01"


async def _activa(session: AsyncSession, **cambios: Any) -> Membership:
    """Socio nuevo con una membresía `active` del 1 al 31 de octubre (plan "Mensual")."""
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, status="active", start=INICIO, **cambios)


async def _contar(session: AsyncSession, tabla: str, record_id: UUID | None = None) -> int:
    return len(await leer_auditoria(session, tabla, record_id))


async def _guardar_politica(session: AsyncSession, **cambios: int) -> None:
    """Guarda la sección `memberships` (Q9, Q11) con los valores por defecto y los cambios."""
    valores = {
        "expiring_days": 7,
        "max_freeze_days_per_membership": 30,
        "max_freezes_per_membership": 2,
        "max_retroactive_days": 7,
        **cambios,
    }
    with actor_scope(ACTOR):
        await update_section(session, "memberships", valores, 0, ACTOR)
        await session.commit()


# Caso feliz (RN-07, N-25) -------------------------------------------------------------------------


async def test_congelar_desde_hoy_deja_frozen_y_corre_el_fin(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    salida = await congelar(
        session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    assert salida.status == "frozen"
    assert (salida.start_date, salida.end_date) == (INICIO, date(2026, 11, 10))
    assert (salida.member_id, salida.member_name, salida.plan_name) == (
        membresia.member_id,
        "Lucía Gómez",
        "Mensual",
    )
    assert salida.agreed_price_cop == 120_000 and salida.paid_cop == 0
    assert [(f.frozen_from, f.frozen_to, f.days) for f in salida.freezes] == [
        (HOY, date(2026, 10, 30), 10)
    ]
    fila = await leer_membresia(session, membresia.id)
    assert fila is not None
    assert (fila["status"], fila["end_date"]) == ("frozen", date(2026, 11, 10))
    congelaciones = await congelaciones_de(session, membresia.id)
    assert [(c["frozen_from"], c["frozen_to"], c["days"]) for c in congelaciones] == [
        (HOY, date(2026, 10, 30), 10)
    ]
    assert congelaciones[0]["created_by"] == ACTOR
    assert salida.freezes[0].id == congelaciones[0]["id"]


async def test_una_congelacion_futura_corre_el_fin_y_deja_active(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    salida = await congelar(
        session,
        ACTOR,
        membership_id=membresia.id,
        frozen_from=date(2026, 10, 25),
        frozen_to=date(2026, 10, 27),
    )
    assert (salida.status, salida.end_date) == ("active", date(2026, 11, 3))
    fila = await leer_membresia(session, membresia.id)
    assert fila is not None and (fila["status"], fila["end_date"]) == ("active", date(2026, 11, 3))


async def test_una_retroactiva_de_7_dias_que_ya_termino_corre_el_fin_y_sigue_active(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Del 14 al 20 de octubre (7 días, Q9): el fin pasa al 7 de noviembre y hoy ya no está
    dentro de la ventana."""
    membresia = await _activa(session)
    salida = await congelar(
        session,
        ACTOR,
        membership_id=membresia.id,
        frozen_from=date(2026, 10, 14),
        frozen_to=date(2026, 10, 20),
    )
    assert (salida.status, salida.end_date) == ("active", date(2026, 11, 7))


# Límites de Q9 desde `settings` ---------------------------------------------------------------


async def test_sin_seccion_guardada_el_tope_es_30_dias(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    membresia_id = membresia.id
    with pytest.raises(FreezeRejected) as error:
        await congelar(
            session,
            ACTOR,
            membership_id=membresia_id,
            frozen_from=HOY,
            frozen_to=date(2026, 11, 20),
        )
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "freeze_days_exceeded",
        None,
    )
    assert await congelaciones_de(session, membresia_id) == []


async def test_los_limites_salen_de_la_seccion_guardada(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    await _guardar_politica(session, max_freeze_days_per_membership=40)
    membresia = await _activa(session)
    salida = await congelar(
        session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=date(2026, 11, 20)
    )
    assert (salida.status, salida.end_date) == ("frozen", date(2026, 12, 1))


async def test_con_cero_congelaciones_permitidas_da_freeze_limit_reached(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    await _guardar_politica(session, max_freezes_per_membership=0)
    membresia = await _activa(session)
    with pytest.raises(FreezeRejected) as error:
        await congelar(session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=HOY)
    assert error.value.code == "freeze_limit_reached"


async def test_segunda_tras_terminar_la_primera_y_tercera_freeze_limit_reached(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    membresia_id = membresia.id
    primera = await congelar(
        session, ACTOR, membership_id=membresia_id, frozen_from=HOY, frozen_to=date(2026, 10, 22)
    )
    assert (primera.status, primera.end_date) == ("frozen", date(2026, 11, 2))
    reloj.advance(days=4)  # 25 de octubre: la primera ya terminó
    segunda = await congelar(
        session,
        ACTOR,
        membership_id=membresia_id,
        frozen_from=date(2026, 10, 25),
        frozen_to=date(2026, 10, 26),
    )
    assert (segunda.status, segunda.end_date) == ("frozen", date(2026, 11, 4))
    assert [(f.frozen_from, f.days) for f in segunda.freezes] == [
        (HOY, 2),
        (date(2026, 10, 25), 2),
    ]
    reloj.advance(days=3)  # 28 de octubre
    with pytest.raises(FreezeRejected) as error:
        await congelar(
            session,
            ACTOR,
            membership_id=membresia_id,
            frozen_from=date(2026, 10, 28),
            frozen_to=date(2026, 10, 28),
        )
    assert (error.value.status, error.value.code) == (409, "freeze_limit_reached")
    assert len(await congelaciones_de(session, membresia_id)) == 2


async def test_una_ya_programada_da_freeze_already_scheduled(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    await make_freeze(session, membresia, date(2026, 10, 25), date(2026, 10, 27))
    with pytest.raises(FreezeRejected) as error:
        await congelar(session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=HOY)
    assert (error.value.status, error.value.code) == (409, "freeze_already_scheduled")


# Rechazos de la regla (D14) ----------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["pending_payment", "cancelled", "expired"])
async def test_un_estado_no_congelable_da_409_membership_not_freezable(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, estado: str
) -> None:
    """Del 20 de septiembre al 20 de octubre: `expired` también por fecha (D5)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status=estado, start=date(2026, 9, 20))
    membresia_id = membresia.id
    with pytest.raises(FreezeRejected) as error:
        await congelar(session, ACTOR, membership_id=membresia_id, frozen_from=HOY, frozen_to=HOY)
    assert (error.value.status, error.value.code, error.value.field) == (
        409,
        "membership_not_freezable",
        None,
    )
    assert await congelaciones_de(session, membresia_id) == []


@pytest.mark.parametrize(
    ("desde", "hasta", "codigo", "campo"),
    [
        (date(2026, 10, 25), date(2026, 10, 24), "validation_error", "frozen_to"),
        (date(2026, 10, 13), date(2026, 10, 20), "freeze_too_retroactive", "frozen_from"),
        (date(2026, 11, 1), date(2026, 11, 2), "freeze_outside_validity", "frozen_from"),
    ],
    ids=["fechas-invertidas", "demasiado-retroactiva", "fuera-de-vigencia"],
)
async def test_la_entrada_mal_formada_da_422_con_su_codigo_y_campo(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    desde: date,
    hasta: date,
    codigo: str,
    campo: str,
) -> None:
    membresia = await _activa(session)
    membresia_id = membresia.id
    with pytest.raises(FreezeRejected) as error:
        await congelar(
            session, ACTOR, membership_id=membresia_id, frozen_from=desde, frozen_to=hasta
        )
    assert (error.value.status, error.value.code, error.value.field) == (422, codigo, campo)
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and (fila["status"], fila["end_date"]) == ("active", FIN)


async def test_una_membresia_inexistente_da_404(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    with pytest.raises(MembershipNotFound) as error:
        await congelar(session, ACTOR, membership_id=uuid4(), frozen_from=HOY, frozen_to=HOY)
    assert (error.value.status, error.value.code) == (404, "membership_not_found")


# Choque con la futura (D14, riesgo 3 de la exploración) -----------------------------------------


async def test_el_fin_corrido_que_choca_con_una_futura_da_409_sin_cambios(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    socio = await make_member(session)
    plan = await make_plan(session)
    actual = await make_membership(session, socio, plan, status="active", start=INICIO)
    futura = await make_membership(session, socio, plan, start=date(2026, 11, 1))
    actual_id, futura_id = actual.id, futura.id
    with pytest.raises(OverlapsFutureMembership) as error:
        await congelar(
            session, ACTOR, membership_id=actual_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
        )
    assert (error.value.status, error.value.code) == (409, "overlaps_future_membership")
    assert error.value.existing_id == futura_id
    assert await congelaciones_de(session, actual_id) == []
    fila = await leer_membresia(session, actual_id)
    assert fila is not None and (fila["status"], fila["end_date"]) == ("active", FIN)
    assert await _contar(session, TABLA_CONGELACIONES) == 0
    acciones = [f["action"] for f in await leer_auditoria(session, TABLA_MEMBRESIAS, actual_id)]
    assert "update" not in acciones


async def test_congelada_y_extendida_junto_a_una_futura_contigua(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """La futura empieza el 11 de noviembre: el fin corrido (10 de noviembre) queda contiguo."""
    socio = await make_member(session)
    plan = await make_plan(session)
    actual = await make_membership(session, socio, plan, status="active", start=INICIO)
    futura = await make_membership(session, socio, plan, start=date(2026, 11, 11))
    salida = await congelar(
        session, ACTOR, membership_id=actual.id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    assert (salida.status, salida.end_date) == ("frozen", date(2026, 11, 10))
    otra = await leer_membresia(session, futura.id)
    assert otra is not None
    assert (otra["status"], otra["start_date"], otra["end_date"]) == (
        "pending_payment",
        date(2026, 11, 11),
        date(2026, 12, 11),
    )
    assert len(await membresias_del_socio(session, socio.id)) == 2


async def test_freeze_traduce_la_exclude_de_membresias_a_overlaps_future_membership(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La `EXCLUDE` de `0008` es la red ante la carrera (D8, D14): sin la revisión previa
    (`lifecycle.find_overlap`), el flush choca con 23P01 y `freeze` responde
    `OverlapsFutureMembership` sin `existing_id` (la base no lo da)."""
    socio = await make_member(session)
    plan = await make_plan(session)
    actual = await make_membership(session, socio, plan, status="active", start=INICIO)
    await make_membership(session, socio, plan, start=date(2026, 11, 1))
    actual_id = actual.id
    monkeypatch.setattr(lifecycle_module, "find_overlap", lambda *args, **kwargs: None)
    with pytest.raises(OverlapsFutureMembership) as error:
        await congelar(
            session, ACTOR, membership_id=actual_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
        )
    assert error.value.code == "overlaps_future_membership"
    assert error.value.existing_id is None
    assert await congelaciones_de(session, actual_id) == []


async def test_otra_membresia_del_socio_no_cambia(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Una vencida del mismo socio (agosto) queda igual."""
    socio = await make_member(session)
    plan = await make_plan(session)
    vieja = await make_membership(session, socio, plan, status="expired", start=date(2026, 8, 1))
    actual = await make_membership(session, socio, plan, status="active", start=INICIO)
    await congelar(session, ACTOR, membership_id=actual.id, frozen_from=HOY, frozen_to=HOY)
    fila = await leer_membresia(session, vieja.id)
    assert fila is not None
    assert (fila["status"], fila["end_date"]) == ("expired", date(2026, 8, 31))


# Auditoría, evento y atomicidad -----------------------------------------------------------------


async def test_la_auditoria_tiene_insert_de_la_congelacion_y_update_de_la_membresia(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    salida = await congelar(
        session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    congelacion_id = salida.freezes[0].id
    filas = await leer_auditoria(session, TABLA_CONGELACIONES, congelacion_id)
    assert [(f["action"], f["subject_member_id"], f["user_id"]) for f in filas] == [
        ("insert", None, ACTOR)
    ]
    despues = filas[0]["after"]
    assert (despues["membership_id"], despues["frozen_from"], despues["frozen_to"]) == (
        str(membresia.id),
        "2026-10-21",
        "2026-10-30",
    )
    assert despues["days"] == 10
    cambios = [
        f
        for f in await leer_auditoria(session, TABLA_MEMBRESIAS, membresia.id)
        if f["action"] == "update"
    ]
    assert [(f["subject_member_id"], f["user_id"]) for f in cambios] == [
        (membresia.member_id, ACTOR)
    ]
    assert cambios[0]["after"] == {"end_date": "2026-11-10", "status": "frozen"}


async def test_congelar_emite_membership_frozen_una_vez(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(MembershipFrozen)
    membresia = await _activa(session)
    await congelar(
        session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
    )
    assert len(recibidos) == 1
    evento = recibidos[0]
    assert (evento.membership_id, evento.member_id) == (membresia.id, membresia.member_id)
    assert (evento.frozen_from, evento.frozen_to, evento.days) == (HOY, date(2026, 10, 30), 10)
    assert evento.end_date == date(2026, 11, 10)


async def test_un_rechazo_no_emite_el_evento(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, capturar_eventos: CapturarEventos
) -> None:
    recibidos = capturar_eventos(MembershipFrozen)
    membresia = await _activa(session)
    with pytest.raises(FreezeRejected):
        await congelar(
            session,
            ACTOR,
            membership_id=membresia.id,
            frozen_from=HOY,
            frozen_to=date(2026, 12, 31),
        )
    assert recibidos == []


class _HandlerRoto(Exception):
    """No es `RuntimeError`: `NotImplementedError` del stub lo es y daría un verde falso."""


async def test_un_handler_que_falla_no_deja_congelacion_ni_cambios_ni_auditoria(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    membresia = await _activa(session)
    membresia_id = membresia.id

    async def roto(evento: MembershipFrozen, sesion: AsyncSession) -> None:
        raise _HandlerRoto

    events.subscribe(MembershipFrozen, roto)  # `restaurar_bus` lo quita al salir
    with pytest.raises(_HandlerRoto), actor_scope(ACTOR):
        await service.freeze(
            session, membership_id=membresia_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
        )
    assert await congelaciones_de(session, membresia_id) == []
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and (fila["status"], fila["end_date"]) == ("active", FIN)
    assert await _contar(session, TABLA_CONGELACIONES) == 0
    acciones = [f["action"] for f in await leer_auditoria(session, TABLA_MEMBRESIAS, membresia_id)]
    assert "update" not in acciones


# Restricciones de la base -------------------------------------------------------------------------


async def test_la_exclude_de_congelaciones_rechaza_ventanas_que_se_cruzan_por_sql_crudo(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """La exploración pide comprobar que `constraint_name` llega en la causa de asyncpg."""
    membresia = await _activa(session)
    insertar = text(
        "INSERT INTO memberships.membership_freezes (id, created_by, membership_id, frozen_from, "
        "frozen_to, days) VALUES (:id, :actor, :m, :desde, :hasta, :dias)"
    )
    base = {"actor": ACTOR, "m": membresia.id}
    await session.execute(
        insertar,
        {**base, "id": uuid4(), "desde": HOY, "hasta": date(2026, 10, 30), "dias": 10},
    )
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            await session.execute(
                insertar,
                {
                    **base,
                    "id": uuid4(),
                    "desde": date(2026, 10, 30),
                    "hasta": date(2026, 10, 31),
                    "dias": 2,
                },
            )
    assert violated_constraint(error.value) == FREEZE_EXCLUDE_NAME
    assert getattr(error.value.orig, "sqlstate", None) == EXCLUSION_VIOLATION


# Orden de candados (D3, L-4: se prueba con una espía de sentencias) -------------------------------


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


async def test_el_candado_del_socio_va_antes_que_el_for_update_de_la_membresia(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, sentencias: list[str]
) -> None:
    membresia = await _activa(session)
    sentencias.clear()
    await congelar(session, ACTOR, membership_id=membresia.id, frozen_from=HOY, frozen_to=HOY)
    socio = next(i for i, s in enumerate(sentencias) if "pg_advisory_xact_lock" in s)
    fila = next(
        i for i, s in enumerate(sentencias) if "FOR UPDATE" in s and "memberships.memberships" in s
    )
    assert socio < fila, sentencias


# Concurrencia (D3, con commit real) ------------------------------------------------------------


async def _intentar(sesion: AsyncSession, membership_id: UUID) -> object:
    with actor_scope(ACTOR):
        try:
            salida = await service.freeze(
                sesion, membership_id=membership_id, frozen_from=HOY, frozen_to=date(2026, 10, 30)
            )
            await sesion.commit()
        except DomainError as error:
            await sesion.rollback()
            return error
    return salida


async def test_dos_congelaciones_simultaneas_una_gana_y_la_otra_es_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
) -> None:
    """La segunda espera el candado del socio, ve la membresía ya `frozen` y responde 409
    `membership_not_freezable`; queda una sola congelación y el fin corrido una sola vez."""
    primera, segunda = dos_sesiones
    membresia = await _activa(primera)
    membresia_id = membresia.id
    resultados = await asyncio.gather(
        _intentar(primera, membresia_id),
        _intentar(segunda, membresia_id),
        return_exceptions=True,  # las dos terminan antes de que `dos_sesiones` limpie
    )
    inesperados = [
        r for r in resultados if isinstance(r, BaseException) and not isinstance(r, DomainError)
    ]
    assert inesperados == [], resultados
    rechazos = [r for r in resultados if isinstance(r, FreezeRejected)]
    ganadoras = [r for r in resultados if not isinstance(r, DomainError)]
    assert len(rechazos) == 1 and len(ganadoras) == 1, resultados
    assert rechazos[0].code == "membership_not_freezable"
    fabrica = async_sessionmaker(primera.bind, expire_on_commit=False)
    async with fabrica() as lectora:
        assert len(await congelaciones_de(lectora, membresia_id)) == 1
        fila = await leer_membresia(lectora, membresia_id)
        assert fila is not None and fila["end_date"] == date(2026, 11, 10)
