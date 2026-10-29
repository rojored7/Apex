"""`DELETE /api/v1/plans/{plan_id}` por HTTP (S4A-B7; US-082; S4A-D24, S4A-D26, S4A-D60).

- admin: 204 sin cuerpo y con `Cache-Control: no-store`; el plan queda dado de baja y `GET
  /plans/{plan_id}` da 404; repetir da 404;
- 409 `plan_has_active_memberships` con el mensaje del conteo ("Este plan tiene N membresías
  activas, desactívalo en su lugar.") y sin `field` ni `existing_id`; una `pending_payment`
  también bloquea (S4A-D24); el plan queda intacto;
- coach y `member` 403 con el plan intacto; sin token 401; 404 si no existe; 422 con
  `field="plan_id"` si no es UUID;
- la escritura 31 del minuto da 429 (`admin-write`, compartida con `POST /plans`).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.plans import make_plan
from tests.plans._apoyo import PLANS, con_membresias, cuerpo, fila_plan, ruta_plan

TOPE_POR_MINUTO = 30


async def test_el_admin_da_de_baja_y_recibe_204_sin_cuerpo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, ["expired", "cancelled"])
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert r.headers["cache-control"] == "no-store"
    fila = await fila_plan(session, plan_id)
    assert fila["deleted_at"] == T0 and fila["is_active"] is False
    r = await app_http.get(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 404, r.text


async def test_repetir_la_baja_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 204, r.text
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "plan_not_found"


@pytest.mark.parametrize(
    ("estados", "mensaje"),
    [
        (["active"] * 3, "Este plan tiene 3 membresías activas, desactívalo en su lugar."),
        (["pending_payment"], "Este plan tiene 1 membresía activa, desactívalo en su lugar."),
    ],
    ids=["tres-activas", "pendiente-de-pago"],
)
async def test_con_membresias_activas_da_409_con_el_conteo_y_el_plan_queda_intacto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    estados: list[str],
    mensaje: str,
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id
    await con_membresias(session, plan, estados)
    antes = await fila_plan(session, plan_id)
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "plan_has_active_memberships"
    assert error["message"] == mensaje
    assert error.get("field") is None and error.get("existing_id") is None
    assert await fila_plan(session, plan_id) == antes


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_y_el_plan_queda_intacto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    plan_id = (await make_plan(session)).id
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    assert (await fila_plan(session, plan_id))["deleted_at"] is None


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    plan_id = (await make_plan(session)).id
    r = await app_http.delete(ruta_plan(plan_id))
    assert r.status_code == 401, r.text
    assert (await fila_plan(session, plan_id))["deleted_at"] is None


@pytest.mark.parametrize("caso", ["inexistente", "dado-de-baja"])
async def test_un_plan_inexistente_o_dado_de_baja_da_404(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caso: str,
) -> None:
    admin = await usuario_real("admin")
    if caso == "inexistente":
        plan_id = uuid4()
    else:
        plan_id = (await make_plan(session, deleted_at=T0 - timedelta(days=1))).id
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "plan_not_found"


async def test_un_plan_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.delete(f"{PLANS}/no-es-uuid", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "plan_id"


# Límite `admin-write` (S4A-D26) ------------------------------------------------------------


async def test_la_31_del_minuto_da_429_y_no_da_de_baja(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    planes = [
        (await make_plan(session, name=f"Plan {i:02d}")).id for i in range(TOPE_POR_MINUTO + 1)
    ]
    for plan_id in planes[:TOPE_POR_MINUTO]:
        r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
        assert r.status_code == 204, r.text
    r = await app_http.delete(ruta_plan(planes[-1]), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert (await fila_plan(session, planes[-1]))["deleted_at"] is None


async def test_la_baja_comparte_admin_write_con_crear_planes(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, name="Base")).id
    for i in range(TOPE_POR_MINUTO):
        r = await app_http.post(PLANS, json=cuerpo(name=f"Plan {i}"), headers=cabeceras(admin))
        assert r.status_code == 201, r.text
    r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert (await fila_plan(session, plan_id))["deleted_at"] is None


async def test_el_403_del_coach_no_consume_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plan_id = (await make_plan(session)).id
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.delete(ruta_plan(plan_id), headers=cabeceras(coach))
        assert r.status_code == 403, r.text
