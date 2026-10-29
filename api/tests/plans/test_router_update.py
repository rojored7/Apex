"""`PATCH /api/v1/plans/{plan_id}` por HTTP (S4A-B7; US-080; S4A-D22, S4A-D26).

- admin: 200 `PlanOut` (con `active_members_count`) y `Cache-Control: no-store`; un cuerpo vacío
  es 200 sin cambios;
- coach y `member` 403 `forbidden` con el plan intacto (y sin consumir cupo); sin token 401;
- 404 `plan_not_found` (inexistente o dado de baja);
- 409 `plan_name_duplicated` con `field="name"` y `existing_id`;
- 422 `validation_error` con `field`: `is_active` o `deleted_at` en el cuerpo (`extra="forbid"`),
  `class_count` incoherente con `kind`, `price_cop` negativo, cero, decimal o texto, `plan_id` que
  no es UUID; el plan queda intacto;
- la escritura 31 del minuto da 429 `rate_limited` (`admin-write`, compartida con `POST /plans`).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.plans import make_plan
from tests.plans._apoyo import CAMPOS_PLAN, PLANS, cuerpo, cuerpo_patch, fila_plan, ruta_plan

TOPE_POR_MINUTO = 30


async def test_el_admin_cambia_el_precio_y_recibe_200_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(price_cop=135_000), headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == CAMPOS_PLAN
    assert (datos["id"], datos["price_cop"]) == (str(plan_id), 135_000)
    assert type(datos["price_cop"]) is int
    assert datos["active_members_count"] == 0
    assert (await fila_plan(session, plan_id))["price_cop"] == 135_000


async def test_un_cuerpo_vacio_da_200_sin_cambios(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    antes = await fila_plan(session, plan_id)
    r = await app_http.patch(ruta_plan(plan_id), json={}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["price_cop"] == 120_000
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
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(price_cop=1), headers=cabeceras(quien)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert (await fila_plan(session, plan_id))["price_cop"] == 120_000


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    plan_id = (await make_plan(session)).id
    r = await app_http.patch(ruta_plan(plan_id), json=cuerpo_patch(price_cop=1))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
    assert (await fila_plan(session, plan_id))["price_cop"] == 120_000


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
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(price_cop=1), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "plan_not_found"


async def test_un_nombre_repetido_da_409_con_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    otro_id = (await make_plan(session, name="Trimestral", duration_days=90)).id
    plan_id = (await make_plan(session)).id
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(name=" trimestral "), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("plan_name_duplicated", "name")
    assert error["existing_id"] == str(otro_id)
    assert (await fila_plan(session, plan_id))["name"] == "Mensual"


_INVALIDOS: list[tuple[dict[str, Any], str]] = [
    (cuerpo_patch(is_active=False), "is_active"),
    (cuerpo_patch(deleted_at="2026-10-21T15:00:00Z"), "deleted_at"),
    (cuerpo_patch(class_count=8), "class_count"),
    (cuerpo_patch(kind="classes"), "class_count"),
    (cuerpo_patch(price_cop=-1), "price_cop"),
    (cuerpo_patch(price_cop=0), "price_cop"),
    (cuerpo_patch(price_cop=120000.5), "price_cop"),
    (cuerpo_patch(price_cop="120000"), "price_cop"),
    (cuerpo_patch(duration_days=0), "duration_days"),
    (cuerpo_patch(name="   "), "name"),
    (cuerpo_patch(name="x" * 81), "name"),
]


@pytest.mark.parametrize(
    ("enviado", "campo"),
    _INVALIDOS,
    ids=[
        "extra-is_active",
        "extra-deleted_at",
        "days-con-clases",
        "classes-sin-clases",
        "precio-negativo",
        "precio-cero",
        "precio-decimal",
        "precio-texto",
        "dias-cero",
        "nombre-blanco",
        "nombre-81",
    ],
)
async def test_un_cuerpo_invalido_da_422_con_field_y_el_plan_queda_intacto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    enviado: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    antes = await fila_plan(session, plan_id)
    r = await app_http.patch(ruta_plan(plan_id), json=enviado, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert await fila_plan(session, plan_id) == antes


async def test_un_plan_id_que_no_es_uuid_da_422_con_field_plan_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.patch(
        f"{PLANS}/no-es-uuid", json=cuerpo_patch(price_cop=1), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "plan_id"


# Límite `admin-write` (S4A-D26) ------------------------------------------------------------


async def test_la_31_del_minuto_da_429_y_no_cambia_el_plan(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session)).id
    for i in range(TOPE_POR_MINUTO):
        r = await app_http.patch(
            ruta_plan(plan_id), json=cuerpo_patch(price_cop=100_000 + i), headers=cabeceras(admin)
        )
        assert r.status_code == 200, r.text
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(price_cop=1), headers=cabeceras(admin)
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert (await fila_plan(session, plan_id))["price_cop"] == 100_000 + TOPE_POR_MINUTO - 1


async def test_editar_comparte_admin_write_con_crear_planes(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan_id = (await make_plan(session, name="Base")).id
    for i in range(TOPE_POR_MINUTO):
        r = await app_http.post(PLANS, json=cuerpo(name=f"Plan {i}"), headers=cabeceras(admin))
        assert r.status_code == 201, r.text
    r = await app_http.patch(
        ruta_plan(plan_id), json=cuerpo_patch(price_cop=1), headers=cabeceras(admin)
    )
    assert r.status_code == 429, r.text
    assert (await fila_plan(session, plan_id))["price_cop"] == 120_000


async def test_el_403_del_coach_no_consume_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plan_id = (await make_plan(session)).id
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.patch(
            ruta_plan(plan_id), json=cuerpo_patch(price_cop=1), headers=cabeceras(coach)
        )
        assert r.status_code == 403, r.text
