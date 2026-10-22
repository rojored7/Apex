"""`POST /api/v1/plans` por HTTP (S2-B9; US-078; DECISIÓN 32, S2-D32).

- admin: 201 `PlanOut` con `price_cop` entero (nunca texto ni decimal) y `created_by` = quien
  llama; "Tiquetera 12" con `class_count`;
- coach y `member` 403 `forbidden`; sin token 401 `unauthorized`; nada se crea;
- 422 `validation_error` con `field`: `price_cop` (`120000.5`, `-1`, `0`, `"120000"`, `true`,
  1.000.000.001, ausente), `duration_days` (0, 3.651, `"30"`), `class_count` (0, 1.001, `days`
  con clases, `classes` sin clases), `name` (`"   "`, 81 caracteres), `kind` y campos que el
  cliente no envía (`extra="forbid"`); nada se crea;
- 409 `plan_name_duplicated` con `field="name"` y `existing_id` para "mensual" tras "Mensual".
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.plans._apoyo import CAMPOS_PLAN, PLANS, cuantos_planes, cuerpo, fila_plan, tiquetera


async def test_el_admin_crea_mensual_y_recibe_201_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANS, json=cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_PLAN
    assert datos["name"] == "Mensual"
    assert datos["price_cop"] == 120_000 and type(datos["price_cop"]) is int
    assert '"price_cop":120000,' in r.text.replace(" ", "")
    assert (datos["kind"], datos["duration_days"], datos["class_count"]) == ("days", 30, None)
    assert datos["is_active"] is True
    fila = await fila_plan(session, UUID(datos["id"]))
    assert fila["created_by"] == admin.id


async def test_el_admin_crea_tiquetera_12(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANS, json=tiquetera(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert (r.json()["kind"], r.json()["class_count"]) == ("classes", 12)


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_y_no_se_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    r = await app_http.post(PLANS, json=cuerpo(), headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await cuantos_planes(session) == 0


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    r = await app_http.post(PLANS, json=cuerpo())
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert await cuantos_planes(session) == 0


_INVALIDOS: list[tuple[dict[str, Any], str]] = [
    (cuerpo(price_cop=120000.5), "price_cop"),
    (cuerpo(price_cop=-1), "price_cop"),
    (cuerpo(price_cop=0), "price_cop"),
    (cuerpo(price_cop="120000"), "price_cop"),
    (cuerpo(price_cop=True), "price_cop"),
    (cuerpo(price_cop=1_000_000_001), "price_cop"),
    ({k: v for k, v in cuerpo().items() if k != "price_cop"}, "price_cop"),
    (cuerpo(duration_days=0), "duration_days"),
    (cuerpo(duration_days=3_651), "duration_days"),
    (cuerpo(duration_days="30"), "duration_days"),
    (tiquetera(class_count=0), "class_count"),
    (tiquetera(class_count=1_001), "class_count"),
    (cuerpo(class_count=8), "class_count"),
    (tiquetera(class_count=None), "class_count"),
    (cuerpo(name="   "), "name"),
    (cuerpo(name="x" * 81), "name"),
    (cuerpo(kind="weeks"), "kind"),
    (cuerpo(is_active=False), "is_active"),
    (cuerpo(created_by="00000000-0000-0000-0000-000000000001"), "created_by"),
]


@pytest.mark.parametrize(
    ("enviado", "campo"),
    _INVALIDOS,
    ids=[
        "precio-decimal",
        "precio-negativo",
        "precio-cero",
        "precio-texto",
        "precio-booleano",
        "precio-tope",
        "precio-ausente",
        "dias-cero",
        "dias-tope",
        "dias-texto",
        "clases-cero",
        "clases-tope",
        "days-con-clases",
        "classes-sin-clases",
        "nombre-blanco",
        "nombre-81",
        "tipo",
        "extra-is_active",
        "extra-created_by",
    ],
)
async def test_un_cuerpo_invalido_da_422_con_field_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    enviado: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANS, json=enviado, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["field"] == campo
    assert await cuantos_planes(session) == 0


async def test_un_nombre_repetido_sin_distinguir_mayusculas_da_409_con_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    primero = await app_http.post(PLANS, json=cuerpo(), headers=cabeceras(admin))
    assert primero.status_code == 201, primero.text
    r = await app_http.post(PLANS, json=cuerpo(name="mensual"), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "plan_name_duplicated"
    assert error["field"] == "name"
    assert error["existing_id"] == primero.json()["id"]
    assert await cuantos_planes(session, nombre="Mensual") == 1
