"""`plans.service.set_active` con PostgreSQL real (S4A-B7; US-081; S4A-D23, S4A-D25).

- Desactivar: `is_active` falso, una fila `update` (`is_active` antes y después, con el actor) y
  `PlanDeactivated(plan_id)` (nunca `PlanUpdated`).
- Activar: una fila `update` y `PlanUpdated(plan_id, changed_fields=("is_active",))` (el catálogo
  no tiene `PlanActivated`).
- Idempotente: repetir no agrega auditoría ni evento y responde el mismo `PlanOut`.
- `PlanNotFound` si no existe o está dado de baja (sin tocar la fila).
- El desactivado no sale en `list(active=True)` y sí en `list(active=False)`.
- La respuesta lleva `active_members_count` (S4A-D25): desactivar no toca las membresías.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.plans import service
from app.modules.plans.exceptions import PlanNotFound
from app.modules.plans.schemas import PlanOut
from app.modules.plans.service import PlanDeactivated, PlanUpdated
from tests.auth._cuentas import filas_auditoria
from tests.conftest import T0, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.plans import make_plan
from tests.plans._apoyo import CAMPOS_PLAN, con_membresias, en_unidad, fila_plan


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def poner(session: AsyncSession, actor: UUID, plan_id: UUID, activo: bool) -> PlanOut:
    return await en_unidad(session, actor, lambda: service.set_active(session, plan_id, activo))


async def updates(session: AsyncSession, plan_id: UUID) -> list[dict[str, Any]]:
    filas = await filas_auditoria(session, "plans.plans", plan_id)
    return [f for f in filas if f["action"] == "update"]


async def test_desactivar_deja_is_active_falso_y_responde_el_plan(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    salida = await poner(session, admin.id, plan.id, False)
    assert isinstance(salida, PlanOut) and set(salida.model_dump()) == CAMPOS_PLAN
    assert (salida.id, salida.is_active) == (plan.id, False)
    fila = await fila_plan(session, plan.id)
    assert fila["is_active"] is False and fila["deleted_at"] is None


async def test_desactivar_deja_una_fila_update_y_emite_plan_deactivated(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    plan = await make_plan(session)
    await poner(session, admin.id, plan.id, False)
    (fila,) = await updates(session, plan.id)
    assert fila["user_id"] == admin.id
    assert (fila["before"], fila["after"]) == ({"is_active": True}, {"is_active": False})
    assert recibidos == [PlanDeactivated(plan_id=plan.id, occurred_at=T0)]


async def test_desactivar_dos_veces_no_agrega_auditoria_ni_evento(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    plan = await make_plan(session)
    await poner(session, admin.id, plan.id, False)
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    salida = await poner(session, admin.id, plan.id, False)
    assert salida.is_active is False
    assert len(await updates(session, plan.id)) == 1
    assert recibidos == []


async def test_activar_emite_plan_updated_con_is_active(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    plan = await make_plan(session, is_active=False)
    salida = await poner(session, admin.id, plan.id, True)
    assert salida.is_active is True
    (fila,) = await updates(session, plan.id)
    assert (fila["before"], fila["after"]) == ({"is_active": False}, {"is_active": True})
    assert recibidos == [
        PlanUpdated(plan_id=plan.id, changed_fields=("is_active",), occurred_at=T0)
    ]


async def test_activar_un_activo_no_agrega_auditoria_ni_evento(
    session: AsyncSession,
    admin: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    recibidos = capturar_eventos(PlanDeactivated, PlanUpdated)
    plan = await make_plan(session)
    salida = await poner(session, admin.id, plan.id, True)
    assert salida.is_active is True
    assert await updates(session, plan.id) == []
    assert recibidos == []


@pytest.mark.parametrize("activo", [True, False])
async def test_un_plan_dado_de_baja_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, activo: bool
) -> None:
    plan = await make_plan(session, is_active=not activo, deleted_at=T0 - timedelta(days=1))
    plan_id = plan.id
    with actor_scope(admin.id), pytest.raises(PlanNotFound):
        await service.set_active(session, plan.id, activo)
    await session.rollback()
    assert (await fila_plan(session, plan_id))["is_active"] is (not activo)


@pytest.mark.parametrize("activo", [True, False])
async def test_un_plan_inexistente_da_plan_not_found(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, activo: bool
) -> None:
    with actor_scope(admin.id), pytest.raises(PlanNotFound):
        await service.set_active(session, uuid4(), activo)


async def test_el_desactivado_no_sale_en_la_lista_de_activos(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock
) -> None:
    plan = await make_plan(session)
    otro = await make_plan(session, name="Trimestral", duration_days=90)
    await poner(session, admin.id, plan.id, False)
    pagina = PageParams(limit=25, offset=0)
    activos = await service.list(session, q=None, active=True, page=pagina, role="admin")
    inactivos = await service.list(session, q=None, active=False, page=pagina, role="admin")
    assert [p.id for p in activos.items] == [otro.id]
    assert [p.id for p in inactivos.items] == [plan.id]


async def test_la_respuesta_lleva_active_members_count_y_las_membresias_no_cambian(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    membresias = await con_membresias(session, plan, ["active", "frozen", "expired"])
    salida = await poner(session, admin.id, plan.id, False)
    assert salida.active_members_count == 2
    for membresia in membresias:
        assert await filas_auditoria(session, "memberships.memberships", membresia.id) != []
        cambios = [
            f
            for f in await filas_auditoria(session, "memberships.memberships", membresia.id)
            if f["action"] == "update"
        ]
        assert cambios == []
