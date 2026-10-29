"""`plans.service.deactivate_or_fail` con PostgreSQL real (S4A-B7; US-082; S4A-D24, S4A-D60).

- Sin membresías activas (solo `expired` y `cancelled`, o ninguna): baja lógica con `deleted_at`
  (la hora del reloj) e `is_active` falso en UNA fila `update` de la auditoría; `PlanDeactivated`
  solo si el plan estaba activo.
- Con membresías activas por estado EFECTIVO (N-22: `active`, `expiring`, `pending_payment` y
  `frozen`; S4A-D24): `PlanHasActiveMemberships(count)` (409 `plan_has_active_memberships`, el
  mensaje con el conteo y sin ids ni nombres, sin `field` ni `existing_id`; S4A-D60) y el plan
  intacto.
- Baja repetida o plan inexistente: `PlanNotFound`. Tras la baja el nombre queda libre para un plan
  nuevo y `get_including_deleted` conserva el nombre; `get` da `PlanNotFound`.
- Toma el plan con `FOR UPDATE` y cuenta con `memberships.service.count_active_by_plan` (perezosa
  G-03).
- Carreras con `dos_sesiones` frente a una venta en vuelo (S4A-D24): si la venta va primero, la
  baja espera su commit y responde 409 con 1; si la baja va primero, la venta espera y recibe
  `PlanInvalid` (sin membresía nueva). Nunca 55P03 ni 40P01.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.db import DatabaseBusy, sqlstate_of
from app.core.errors import DomainError
from app.modules.memberships import service as memberships_service
from app.modules.memberships.exceptions import PlanInvalid
from app.modules.plans import service
from app.modules.plans.exceptions import PlanHasActiveMemberships, PlanNotFound
from app.modules.plans.service import PlanDeactivated, PlanUpdated
from tests.auth._cuentas import filas_auditoria
from tests.conftest import T0, CapturarEventos, ContadorDeConsultas, CrearUsuario, UsuarioPrueba
from tests.factories.members import make_member
from tests.factories.plans import make_plan
from tests.plans._apoyo import con_membresias, en_unidad, entrada, fila_plan

ACTOR = UUID("0000000a-0000-4000-8000-00000000b207")
"""Actor de las carreras: `dos_sesiones` no se combina con `session` (ni con `usuario_real`)."""
SQLSTATES_PROHIBIDOS = frozenset({"55P03", "40P01"})
ESPERA_S = 0.5


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def dar_de_baja(session: AsyncSession, actor: UUID, plan_id: UUID) -> None:
    await en_unidad(session, actor, lambda: service.deactivate_or_fail(session, plan_id))


async def updates(session: AsyncSession, plan_id: UUID) -> list[dict[str, Any]]:
    filas = await filas_auditoria(session, "plans.plans", plan_id)
    return [f for f in filas if f["action"] == "update"]


# Baja ---------------------------------------------------------------------------------------


async def test_solo_vencidas_y_anuladas_da_de_baja_en_una_fila_update(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    await con_membresias(session, plan, ["expired", "cancelled", "expired"])
    await dar_de_baja(session, admin.id, plan.id)
    fila = await fila_plan(session, plan.id)
    assert fila["deleted_at"] == reloj.now_utc()
    assert fila["is_active"] is False
    (auditoria,) = await updates(session, plan.id)
    assert auditoria["user_id"] == admin.id
    assert auditoria["before"] == {"deleted_at": None, "is_active": True}
    assert set(auditoria["after"]) == {"deleted_at", "is_active"}
    assert auditoria["after"]["is_active"] is False and auditoria["after"]["deleted_at"]


async def test_sin_membresias_da_de_baja(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    await dar_de_baja(session, admin.id, plan.id)
    assert (await fila_plan(session, plan.id))["deleted_at"] == reloj.now_utc()


async def test_la_baja_de_un_activo_emite_plan_deactivated(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    plan = await make_plan(session)
    await dar_de_baja(session, admin.id, plan.id)
    assert recibidos == [PlanDeactivated(plan_id=plan.id, occurred_at=T0)]


async def test_la_baja_de_un_inactivo_no_emite_y_solo_cambia_deleted_at(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    plan = await make_plan(session, is_active=False)
    await dar_de_baja(session, admin.id, plan.id)
    assert recibidos == []
    (auditoria,) = await updates(session, plan.id)
    assert auditoria["before"] == {"deleted_at": None}
    assert (await fila_plan(session, plan.id))["deleted_at"] == reloj.now_utc()


# Con membresías activas ---------------------------------------------------------------------


async def test_con_12_activas_da_plan_has_active_memberships_y_el_plan_queda_intacto(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, ["active"] * 12)
    antes = await fila_plan(session, plan.id)
    with actor_scope(admin.id), pytest.raises(PlanHasActiveMemberships) as error:
        await service.deactivate_or_fail(session, plan.id)
    await session.rollback()
    assert (error.value.status, error.value.code) == (409, "plan_has_active_memberships")
    assert error.value.count == 12
    assert error.value.message == "Este plan tiene 12 membresías activas, desactívalo en su lugar."
    assert await fila_plan(session, plan_id) == antes
    assert await updates(session, plan_id) == []


@pytest.mark.parametrize("estado", ["active", "expiring", "pending_payment", "frozen"])
async def test_una_membresia_activa_por_estado_efectivo_bloquea_la_baja(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    bus_listo: Keyring,
    estado: str,
) -> None:
    """S4A-D24: `pending_payment` cuenta como activa (P2-1: se anula antes de dar de baja)."""
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, [estado, "expired", "cancelled"])
    with actor_scope(admin.id), pytest.raises(PlanHasActiveMemberships) as error:
        await service.deactivate_or_fail(session, plan.id)
    await session.rollback()
    assert error.value.count == 1
    assert error.value.message == "Este plan tiene 1 membresía activa, desactívalo en su lugar."
    assert (await fila_plan(session, plan_id))["deleted_at"] is None


async def test_cuenta_todas_las_activas_y_no_las_vencidas_ni_anuladas(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    estados = ["active", "expiring", "pending_payment", "frozen", "expired", "cancelled"]
    await con_membresias(session, plan, estados)
    with actor_scope(admin.id), pytest.raises(PlanHasActiveMemberships) as error:
        await service.deactivate_or_fail(session, plan.id)
    assert error.value.count == 4


async def test_el_409_solo_lleva_el_conteo(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session, name="Plan Secreto")
    (membresia,) = await con_membresias(session, plan, ["active"])
    with actor_scope(admin.id), pytest.raises(PlanHasActiveMemberships) as error:
        await service.deactivate_or_fail(session, plan.id)
    cuerpo = error.value.body().model_dump()
    assert cuerpo["field"] is None and cuerpo["existing_id"] is None
    texto = str(cuerpo)
    for dato in ("Plan Secreto", str(plan.id), str(membresia.id), str(membresia.member_id)):
        assert dato not in texto


# Después de la baja -------------------------------------------------------------------------


async def test_la_baja_repetida_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    plan_id = plan.id
    await dar_de_baja(session, admin.id, plan.id)
    with actor_scope(admin.id), pytest.raises(PlanNotFound):
        await service.deactivate_or_fail(session, plan.id)
    await session.rollback()
    assert len(await updates(session, plan_id)) == 1


async def test_un_plan_inexistente_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    with actor_scope(admin.id), pytest.raises(PlanNotFound):
        await service.deactivate_or_fail(session, uuid4())


async def test_el_nombre_queda_libre_para_un_plan_nuevo(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session, name="Mensual")
    await dar_de_baja(session, admin.id, plan.id)
    nuevo = await en_unidad(session, admin.id, lambda: service.create(session, entrada()))
    assert nuevo.name == "Mensual" and nuevo.id != plan.id
    assert nuevo.active_members_count == 0


async def test_get_including_deleted_conserva_el_nombre_y_get_no_lo_ve(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session, name="Bimestral", duration_days=60)
    await dar_de_baja(session, admin.id, plan.id)
    foto = await service.get_including_deleted(session, plan.id)
    assert (foto.name, foto.is_active) == ("Bimestral", False)
    assert foto.deleted_at == reloj.now_utc()
    with pytest.raises(PlanNotFound):
        await service.get(session, plan.id)
    assert await service.names_for(session, [plan.id]) == {plan.id: "Bimestral"}


# Candado y contrato con memberships ---------------------------------------------------------


async def test_toma_el_plan_con_for_update(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    plan = await make_plan(session)
    with contador_de_consultas.midiendo() as medido:
        await dar_de_baja(session, admin.id, plan.id)
    candados = [
        sql
        for sql in medido.sentencias
        if "plans.plans" in sql and "FOR UPDATE" in sql.upper() and "FOR SHARE" not in sql.upper()
    ]
    assert candados, medido.sentencias


async def test_cuenta_con_count_active_by_plan_de_memberships(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[UUID] = []
    original = memberships_service.count_active_by_plan

    async def espia(sesion: AsyncSession, plan_id: UUID) -> int:
        llamadas.append(plan_id)
        return await original(sesion, plan_id)

    monkeypatch.setattr(memberships_service, "count_active_by_plan", espia)
    plan = await make_plan(session)
    await dar_de_baja(session, admin.id, plan.id)
    assert llamadas == [plan.id]


# Carreras con una venta en vuelo (S4A-D24) ---------------------------------------------------


async def _en_transaccion(
    sesion: AsyncSession, operacion: Callable[[], Awaitable[object]], *, confirmar: bool
) -> object:
    """Corre `operacion` bajo `ACTOR` con `lock_timeout` de 5 s; devuelve la salida o el error."""
    with actor_scope(ACTOR):
        try:
            await sesion.execute(text("SET LOCAL lock_timeout = '5s'"))
            salida = await operacion()
            if confirmar:
                await sesion.commit()
        except (DomainError, DBAPIError) as error:
            await sesion.rollback()
            return error
    return salida


def _vender(
    sesion: AsyncSession, member_id: UUID, plan_id: UUID
) -> Callable[[], Awaitable[object]]:
    return lambda: memberships_service.sell(sesion, member_id=member_id, plan_id=plan_id)


def _prohibido(resultado: object) -> bool:
    return isinstance(resultado, DatabaseBusy) or (
        isinstance(resultado, DBAPIError) and sqlstate_of(resultado) in SQLSTATES_PROHIBIDOS
    )


async def test_con_una_venta_en_vuelo_la_baja_espera_el_commit_y_da_409(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    plan = await make_plan(primera)
    venta = await _en_transaccion(primera, _vender(primera, socio.id, plan.id), confirmar=False)
    assert not isinstance(venta, BaseException), venta  # la venta tiene el `FOR SHARE` del plan
    baja = asyncio.create_task(
        _en_transaccion(
            segunda, lambda: service.deactivate_or_fail(segunda, plan.id), confirmar=True
        )
    )
    await asyncio.sleep(ESPERA_S)
    assert not baja.done(), "la baja debía esperar el candado de la venta"
    await primera.commit()
    resultado = await asyncio.wait_for(baja, timeout=10)
    assert not _prohibido(resultado), resultado
    assert isinstance(resultado, PlanHasActiveMemberships), resultado
    assert resultado.count == 1
    fila = (
        await primera.execute(
            text("SELECT deleted_at, is_active FROM plans.plans WHERE id = :id"), {"id": plan.id}
        )
    ).one()
    assert (fila.deleted_at, fila.is_active) == (None, True)


async def test_si_la_baja_gana_la_venta_espera_y_recibe_plan_invalid(
    dos_sesiones: tuple[AsyncSession, AsyncSession], bus_confirmado: Keyring, reloj: FrozenClock
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    plan = await make_plan(primera)
    plan_id = plan.id  # el rollback de la venta expira `plan` en `primera`
    baja = await _en_transaccion(
        segunda, lambda: service.deactivate_or_fail(segunda, plan.id), confirmar=False
    )
    assert baja is None, baja  # la baja tiene el `FOR UPDATE` del plan
    venta = asyncio.create_task(
        _en_transaccion(primera, _vender(primera, socio.id, plan.id), confirmar=True)
    )
    await asyncio.sleep(ESPERA_S)
    assert not venta.done(), "la venta debía esperar el candado de la baja"
    await segunda.commit()
    resultado = await asyncio.wait_for(venta, timeout=10)
    assert not _prohibido(resultado), resultado
    assert isinstance(resultado, PlanInvalid), resultado
    vendidas = await primera.scalar(
        text("SELECT count(*) FROM memberships.memberships WHERE plan_id = :id"), {"id": plan_id}
    )
    assert vendidas == 0
