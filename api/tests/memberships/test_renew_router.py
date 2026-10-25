"""Renovar por HTTP y vista previa de la renovación (S3-B6, US-088; Q1, D27, H-2, S3-D42).

Renovar es `POST /api/v1/members/{member_id}/memberships` con `renew: true` (D5: un solo
endpoint). S3-B6 quita el validador provisional de B1 (revisión de seguridad de B1, M1) que
respondía 422 `field="renew"`: `tests/memberships/test_sell_router_renew.py` se retira y sus dos
casos quedan aquí invertidos (`renew: true` vende; `renew: false` explícito sigue vendiendo).

- admin y coach: 201 `SellMembershipOut` con inicio el día siguiente al fin de la vigente; 409
  `future_membership_exists` con envelope y `existing_id`; `member` 403; sin token 401;
- límite `memberships-write` (30 por minuto por usuario): la renovación 31 del mismo usuario da 429
  (las 30 primeras van a un socio inexistente y dan 404: el límite se cuenta antes del service);
- `GET /api/v1/members/{member_id}/memberships/renewal-preview?plan_id=` (admin y coach): 200
  `RenewalPreviewOut` con las claves exactas y `no-store`; 404 `member_not_found`; 409
  `future_membership_exists`; 422 con `field="plan_id"` si falta o no es UUID, y `plan_inactive`;
  `member` 403; sin token 401; es una lectura: 40 seguidas del mismo coach no dan 429 y no gastan
  el cupo de `memberships-write` (el mismo coach sigue vendiendo);
- OpenAPI de la vista previa: 200, 401, 403, 404, 409, 422, 500 y 503 (sin 429), respuesta
  `RenewalPreviewOut` y `plan_id` como parámetro de query obligatorio.

"Hoy" es 2026-10-21 (`reloj` de `api_prueba`). La vigente "Mensual" (120.000, 30 días) va del
2026-09-28 al 2026-10-28; la renovación, del 2026-10-29 al 2026-11-28.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import CAMPOS_SELL, cuerpo_venta, membresias_del_socio, ruta_venta

RUTA_PREVIA_OPENAPI = "/api/v1/members/{member_id}/memberships/renewal-preview"
TOPE_POR_MINUTO = 30
CAMPOS_PREVIA = frozenset({"start_date", "end_date", "agreed_price_cop", "current_end_date"})


def ruta_previa(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/memberships/renewal-preview"


async def _con_vigente(session: AsyncSession) -> tuple[UUID, UUID, UUID]:
    """(socio, plan, vigente): `active` del 2026-09-28 al 2026-10-28."""
    socio = await make_member(session)
    plan = await make_plan(session)
    vigente = await make_membership(session, socio, plan, status="active", start=date(2026, 9, 28))
    return socio.id, plan.id, vigente.id


# Renovar ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_renovar_da_201_desde_el_dia_siguiente_al_fin_de_la_vigente(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    socio_id, plan_id, _vigente_id = await _con_vigente(session)
    r = await app_http.post(
        ruta_venta(socio_id),
        json=cuerpo_venta(plan_id, renew=True, start_date="2026-12-01"),
        headers=cabeceras(quien),
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_SELL
    assert (datos["start_date"], datos["end_date"]) == ("2026-10-29", "2026-11-28")
    assert (datos["status"], datos["first_payment_id"]) == ("pending_payment", None)
    assert "no-store" in r.headers.get("cache-control", "")
    assert len(await membresias_del_socio(session, socio_id)) == 2


async def test_renew_false_explicito_sigue_vendiendo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """Invertido de `test_sell_router_renew.py` (B1): el booleano explícito no cambia la venta."""
    admin = await usuario_real("admin")
    socio = await make_member(session)
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id, renew=False), headers=cabeceras(admin)
    )
    assert r.status_code == 201, r.text
    assert (r.json()["status"], r.json()["start_date"]) == ("pending_payment", "2026-10-21")


async def test_renew_true_ya_no_es_un_422_de_forma(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """Invertido de `test_sell_router_renew.py` (B1): sin vigente, renovar vende desde hoy."""
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id, renew=True), headers=cabeceras(coach)
    )
    assert r.status_code == 201, r.text
    assert (r.json()["start_date"], r.json()["end_date"]) == ("2026-10-21", "2026-11-20")


async def test_con_una_futura_da_409_future_membership_exists_con_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    plan = await make_plan(session)
    await make_membership(session, socio, plan, status="active", start=date(2026, 9, 28))
    futura = await make_membership(session, socio, plan, start=date(2026, 10, 29))
    socio_id, plan_id, futura_id = socio.id, plan.id, futura.id
    r = await app_http.post(
        ruta_venta(socio_id), json=cuerpo_venta(plan_id, renew=True), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    error = r.json()["error"]
    assert (error["code"], error["existing_id"]) == ("future_membership_exists", str(futura_id))
    assert len(await membresias_del_socio(session, socio_id)) == 2


async def test_un_member_recibe_403_y_no_renueva(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    quien = await usuario_real("member")
    socio_id, plan_id, _vigente_id = await _con_vigente(session)
    r = await app_http.post(
        ruta_venta(socio_id), json=cuerpo_venta(plan_id, renew=True), headers=cabeceras(quien)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert len(await membresias_del_socio(session, socio_id)) == 1


async def test_renovar_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.post(ruta_venta(uuid4()), json=cuerpo_venta(uuid4(), renew=True))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_la_renovacion_31_del_mismo_usuario_en_un_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    inexistente = ruta_venta(uuid4())
    cuerpo = cuerpo_venta(uuid4(), renew=True)
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(inexistente, json=cuerpo, headers=cabeceras(coach))
        assert r.status_code == 404, r.text
    r = await app_http.post(inexistente, json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(inexistente, json=cuerpo, headers=cabeceras(otro))
    assert r.status_code == 404, r.text


# Vista previa -----------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_la_vista_previa_da_200_con_el_contrato_y_no_escribe(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    socio_id, plan_id, _vigente_id = await _con_vigente(session)
    r = await app_http.get(
        ruta_previa(socio_id), params={"plan_id": str(plan_id)}, headers=cabeceras(quien)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "start_date": "2026-10-29",
        "end_date": "2026-11-28",
        "agreed_price_cop": 120_000,
        "current_end_date": "2026-10-28",
    }
    assert set(r.json()) == CAMPOS_PREVIA
    assert "no-store" in r.headers.get("cache-control", "")
    assert len(await membresias_del_socio(session, socio_id)) == 1


async def test_la_vista_previa_de_un_socio_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    plan = await make_plan(session)
    r = await app_http.get(
        ruta_previa(uuid4()), params={"plan_id": str(plan.id)}, headers=cabeceras(coach)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_la_vista_previa_con_una_futura_da_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    futura = await make_membership(session, socio, plan, start=date(2026, 10, 29))
    socio_id, plan_id, futura_id = socio.id, plan.id, futura.id
    r = await app_http.get(
        ruta_previa(socio_id), params={"plan_id": str(plan_id)}, headers=cabeceras(coach)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["existing_id"]) == ("future_membership_exists", str(futura_id))


@pytest.mark.parametrize("params", [{}, {"plan_id": "plan-1"}], ids=["ausente", "no-uuid"])
async def test_la_vista_previa_sin_plan_id_valido_da_422_en_plan_id(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    params: dict[str, str],
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_previa(uuid4()), params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "plan_id")


async def test_la_vista_previa_con_un_plan_inactivo_da_422_plan_inactive(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio_id, _plan_id, _vigente_id = await _con_vigente(session)
    inactivo = await make_plan(session, name="Viejo", is_active=False)
    inactivo_id = inactivo.id
    r = await app_http.get(
        ruta_previa(socio_id), params={"plan_id": str(inactivo_id)}, headers=cabeceras(coach)
    )
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("plan_inactive", "plan_id")


async def test_la_vista_previa_para_member_da_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    quien = await usuario_real("member")
    params = {"plan_id": str(uuid4())}
    r = await app_http.get(ruta_previa(uuid4()), params=params, headers=cabeceras(quien))
    assert r.status_code == 403, r.text
    r = await app_http.get(ruta_previa(uuid4()), params=params)
    assert r.status_code == 401, r.text


async def test_la_vista_previa_no_tiene_limite_ni_gasta_el_cupo_de_escritura(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio_id, plan_id, _vigente_id = await _con_vigente(session)
    otro = await make_member(session, document=unique_document())
    otro_id = otro.id
    for _ in range(TOPE_POR_MINUTO + 10):
        r = await app_http.get(
            ruta_previa(socio_id), params={"plan_id": str(plan_id)}, headers=cabeceras(coach)
        )
        assert r.status_code == 200, r.text
    r = await app_http.post(
        ruta_venta(otro_id), json=cuerpo_venta(plan_id), headers=cabeceras(coach)
    )
    assert r.status_code == 201, r.text


async def test_el_openapi_de_la_vista_previa_declara_sus_errores(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][RUTA_PREVIA_OPENAPI]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "404", "409", "422", "500", "503"}
    assert operacion["tags"] == ["memberships"]
    exito = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert exito["$ref"] == "#/components/schemas/RenewalPreviewOut"
    parametros = {p["name"]: p for p in operacion["parameters"]}
    assert parametros["plan_id"]["in"] == "query" and parametros["plan_id"]["required"] is True
