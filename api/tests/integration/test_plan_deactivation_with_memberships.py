"""US-081 con membresías vigentes (S4A-B7; S4A-D23; RN-08).

`plans.service.set_active` y `memberships.service.sell` reales sobre PostgreSQL:
- con cuatro membresías vigentes del plan (`active`, `expiring`, `pending_payment` y `frozen`),
  desactivarlo no cambia su estado guardado ni su estado efectivo, precio, fechas ni clases, y no
  deja filas `update` de `memberships.memberships` en la auditoría;
- vender ese plan inactivo da `PlanInactive` (422 `plan_inactive`) por el service y por HTTP, y no
  crea la membresía; al reactivarlo se vende otra vez.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.memberships import service as memberships_service
from app.modules.memberships.exceptions import PlanInactive
from app.modules.plans import service as plans_service
from tests.auth._cuentas import filas_auditoria
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.members import make_members
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    cuerpo_venta,
    leer_membresia,
    membresias_del_socio,
    ruta_venta,
    vender,
)
from tests.plans._apoyo import con_membresias, en_unidad

VIGENTES = ["active", "expiring", "pending_payment", "frozen"]
CLAVES = (
    "status",
    "agreed_price_cop",
    "start_date",
    "end_date",
    "classes_total",
    "classes_remaining",
)


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def desactivar(session: AsyncSession, actor: UUID, plan_id: UUID) -> Any:
    return await en_unidad(
        session, actor, lambda: plans_service.set_active(session, plan_id, False)
    )


async def test_desactivar_no_cambia_las_cuatro_membresias_vigentes(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    membresias = await con_membresias(session, plan, VIGENTES)
    antes = {m.id: await leer_membresia(session, m.id) for m in membresias}
    efectivos_antes = await memberships_service.status_for(
        session, [m.member_id for m in membresias]
    )

    salida = await desactivar(session, admin.id, plan.id)

    assert salida.is_active is False
    assert salida.active_members_count == 4
    for membresia in membresias:
        despues = await leer_membresia(session, membresia.id)
        assert despues is not None
        previa = antes[membresia.id]
        assert previa is not None
        assert {k: despues[k] for k in CLAVES} == {k: previa[k] for k in CLAVES}
        filas = await filas_auditoria(session, "memberships.memberships", membresia.id)
        assert [f["action"] for f in filas] == ["insert"]
    efectivos = await memberships_service.status_for(session, [m.member_id for m in membresias])
    assert {k: v.status for k, v in efectivos.items()} == {
        k: v.status for k, v in efectivos_antes.items()
    }
    assert sorted(v.status for v in efectivos.values()) == sorted(VIGENTES)


async def test_vender_un_plan_desactivado_da_plan_inactive_y_no_crea_nada(
    session: AsyncSession, admin: UsuarioPrueba, reloj: FrozenClock, bus_listo: Keyring
) -> None:
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, VIGENTES)
    (socio,) = await make_members(session, 1)
    socio_id = socio.id
    await desactivar(session, admin.id, plan.id)
    with actor_scope(admin.id), pytest.raises(PlanInactive) as error:
        await memberships_service.sell(session, member_id=socio.id, plan_id=plan.id)
    await session.rollback()
    assert (error.value.status, error.value.code) == (422, "plan_inactive")
    assert await membresias_del_socio(session, socio_id) == []

    await en_unidad(session, admin.id, lambda: plans_service.set_active(session, plan_id, True))
    vendida = await vender(session, admin.id, member_id=socio_id, plan_id=plan_id)
    assert vendida.plan_id == plan_id


async def test_por_http_la_venta_de_un_plan_desactivado_da_422_plan_inactive(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
    bus_listo: Keyring,
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    (socio,) = await make_members(session, 1)
    socio_id = socio.id
    r = await app_http.post(f"/api/v1/plans/{plan.id}/deactivate", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    r = await app_http.post(
        ruta_venta(socio_id), json=cuerpo_venta(plan.id), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "plan_inactive"
    assert await membresias_del_socio(session, socio_id) == []
