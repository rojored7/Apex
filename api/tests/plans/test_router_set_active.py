"""`POST /api/v1/plans/{plan_id}/activate` y `/deactivate` por HTTP (S4A-B7; US-081; S4A-D23,
S4A-D26).

- admin: 200 `PlanOut` con el `is_active` nuevo, `active_members_count` y `Cache-Control:
  no-store`; repetir es idempotente (200 igual);
- coach y `member` 403 con el plan intacto; sin token 401;
- 404 `plan_not_found` (inexistente o dado de baja); 422 con `field="plan_id"` si no es UUID;
- la escritura 31 del minuto da 429 (`admin-write`, compartida con `POST /plans`); el 403 del coach
  no consume cupo;
- el plan desactivado no sale en `GET /plans?active=true` y sí en `active=false`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.plans import make_plan
from tests.plans._apoyo import CAMPOS_PLAN, PLANS, con_membresias, cuerpo, fila_plan, ruta_plan

TOPE_POR_MINUTO = 30
ACCIONES = {"activate": True, "deactivate": False}


@pytest.mark.parametrize("accion", sorted(ACCIONES))
async def test_el_admin_cambia_is_active_y_recibe_200_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    accion: str,
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, is_active=not ACCIONES[accion])).id
    r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_PLAN
    assert (datos["id"], datos["is_active"]) == (str(plan_id), ACCIONES[accion])
    assert (await fila_plan(session, plan_id))["is_active"] is ACCIONES[accion]


@pytest.mark.parametrize("accion", sorted(ACCIONES))
async def test_repetir_es_idempotente(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    accion: str,
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, is_active=ACCIONES[accion])).id
    for _ in range(2):
        r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(admin))
        assert r.status_code == 200, r.text
        assert r.json()["is_active"] is ACCIONES[accion]


async def test_desactivar_responde_active_members_count(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, ["active", "pending_payment", "cancelled"])
    r = await app_http.post(ruta_plan(plan_id, "deactivate"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["active_members_count"] == 2


@pytest.mark.parametrize("accion", sorted(ACCIONES))
@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_y_el_plan_queda_intacto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
    accion: str,
) -> None:
    quien = await usuario_real(rol)
    plan_id = (await make_plan(session, is_active=not ACCIONES[accion])).id
    r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    assert (await fila_plan(session, plan_id))["is_active"] is (not ACCIONES[accion])


@pytest.mark.parametrize("accion", sorted(ACCIONES))
async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession, accion: str) -> None:
    plan_id = (await make_plan(session)).id
    r = await app_http.post(ruta_plan(plan_id, accion))
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("accion", sorted(ACCIONES))
@pytest.mark.parametrize("caso", ["inexistente", "dado-de-baja"])
async def test_un_plan_inexistente_o_dado_de_baja_da_404(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caso: str,
    accion: str,
) -> None:
    admin = await usuario_real("admin")
    if caso == "inexistente":
        plan_id = uuid4()
    else:
        plan_id = (await make_plan(session, deleted_at=T0 - timedelta(days=1))).id
    r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "plan_not_found"


@pytest.mark.parametrize("accion", sorted(ACCIONES))
async def test_un_plan_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, accion: str
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(f"{PLANS}/no-es-uuid/{accion}", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "plan_id"


async def test_el_desactivado_sale_solo_en_la_lista_de_inactivos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    r = await app_http.post(ruta_plan(plan_id, "deactivate"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    activos = await app_http.get(PLANS, params={"active": "true"}, headers=cabeceras(admin))
    inactivos = await app_http.get(PLANS, params={"active": "false"}, headers=cabeceras(admin))
    assert [p["id"] for p in activos.json()["items"]] == []
    assert [p["id"] for p in inactivos.json()["items"]] == [str(plan_id)]
    assert (activos.json()["total"], inactivos.json()["total"]) == (0, 1)


# Límite `admin-write` (S4A-D26) ------------------------------------------------------------


@pytest.mark.parametrize("accion", sorted(ACCIONES))
async def test_la_31_del_minuto_da_429(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    accion: str,
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, is_active=ACCIONES[accion])).id
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(admin))
        assert r.status_code == 200, r.text
    r = await app_http.post(ruta_plan(plan_id, accion), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"


async def test_desactivar_comparte_admin_write_con_crear_planes(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, name="Base")).id
    for i in range(TOPE_POR_MINUTO):
        r = await app_http.post(PLANS, json=cuerpo(name=f"Plan {i}"), headers=cabeceras(admin))
        assert r.status_code == 201, r.text
    r = await app_http.post(ruta_plan(plan_id, "deactivate"), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert (await fila_plan(session, plan_id))["is_active"] is True


async def test_el_403_del_coach_no_consume_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plan_id = (await make_plan(session)).id
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.post(ruta_plan(plan_id, "deactivate"), headers=cabeceras(coach))
        assert r.status_code == 403, r.text
