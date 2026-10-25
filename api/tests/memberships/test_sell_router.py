"""`POST /api/v1/members/{member_id}/memberships` por HTTP (S3-B1, US-084; blueprint B1 "Rojo";
H-2, S3-D42, D16, D27).

- admin y coach: 201 `SellMembershipOut` con las claves exactas, montos enteros JSON y
  `Cache-Control: no-store`; `member` 403; sin token 401;
- 404 `member_not_found`; 422 `plan_invalid` con `field="plan_id"`; 409 con envelope y
  `existing_id`;
- 422 de forma con `field`: `plan_id` ausente o no UUID, `start_date` mal formada, `renew` que no
  es booleano estricto, campos desconocidos (incluido `agreed_price_cop`, D16) y, desde S3-B4 (D4),
  un `first_payment` mal formado con `field="first_payment.<campo>"`; nada se crea;
- S3-B4 (D4, M-8): con `first_payment` que cubre el precio, 201 `active` con `paid_cop` y
  `first_payment_id`; el rol sale del principal: el coach con `paid_at` de hace 8 días recibe 422
  `paid_at_too_retroactive` con `field="first_payment.paid_at"` y el admin vende con ese pago;
- límite `memberships-write` (30 por minuto por usuario, S3-D42): la petición 31 del mismo
  usuario da 429 con `Retry-After`, la de otro usuario pasa; el límite se cuenta antes del service
  (las 30 primeras van a un socio inexistente y dan 404);
- OpenAPI de la ruta: 201, 401, 403, 404, 409, 422, 429, 500 y 503 (D27; el 503 `busy` lo agrega
  el gancho de S3-D67).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import CAMPOS_SELL, cuerpo_venta, membresias_del_socio, ruta_venta

RUTA_OPENAPI = "/api/v1/members/{member_id}/memberships"
TOPE_POR_MINUTO = 30


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_venden_y_reciben_201_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    socio = await make_member(session)
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id), headers=cabeceras(quien)
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_SELL
    assert datos["status"] == "pending_payment"
    assert (datos["start_date"], datos["end_date"]) == ("2026-10-21", "2026-11-20")
    assert datos["agreed_price_cop"] == 120_000 and type(datos["agreed_price_cop"]) is int
    assert datos["paid_cop"] == 0 and type(datos["paid_cop"]) is int
    assert '"agreed_price_cop":120000,' in r.text.replace(" ", "")
    assert (datos["member_id"], datos["plan_id"]) == (str(socio.id), str(plan.id))
    assert (datos["member_name"], datos["plan_name"]) == ("Lucía Gómez", "Mensual")
    assert datos["freezes"] == [] and datos["first_payment_id"] is None
    assert "no-store" in r.headers.get("cache-control", "")
    filas = await membresias_del_socio(session, socio.id)
    assert [f["id"] for f in filas] == [UUID(datos["id"])]
    assert filas[0]["created_by"] == quien.id


async def test_member_recibe_403_y_no_se_crea_nada(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    socio_usuario = await usuario_real("member")
    socio = await make_member(session)
    socio_id = socio.id  # tras un error la sesión revierte y el ORM expira (MissingGreenlet)
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id), headers=cabeceras(socio_usuario)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await membresias_del_socio(session, socio_id) == []


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    r = await app_http.post(ruta_venta(uuid4()), json=cuerpo_venta(uuid4()))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_socio_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    plan = await make_plan(session)
    r = await app_http.post(
        ruta_venta(uuid4()), json=cuerpo_venta(plan.id), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_plan_inexistente_da_422_plan_invalid(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(uuid4()), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "plan_invalid"
    assert r.json()["error"]["field"] == "plan_id"


async def test_con_vigente_da_409_con_envelope_y_existing_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    plan = await make_plan(session)
    previa = await make_membership(session, socio, plan, status="active")
    previa_id = previa.id  # tras el 409 la sesión revierte y el ORM expira
    r = await app_http.post(
        ruta_venta(socio.id), json=cuerpo_venta(plan.id), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "membership_conflict"
    assert error["existing_id"] == str(previa_id)
    assert set(r.json()) == {"error"}


def _sin(campo: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cuerpo.items() if k != campo}


_PLAN = "11111111-2222-3333-4444-555555555555"
_INVALIDOS: list[tuple[dict[str, Any], str]] = [
    (_sin("plan_id", cuerpo_venta(_PLAN)), "plan_id"),
    (cuerpo_venta("no-es-uuid"), "plan_id"),
    (cuerpo_venta(_PLAN, start_date="2026-13-01"), "start_date"),
    (cuerpo_venta(_PLAN, start_date="21/10/2026"), "start_date"),
    (cuerpo_venta(_PLAN, renew="true"), "renew"),
    (cuerpo_venta(_PLAN, agreed_price_cop=1), "agreed_price_cop"),
    (cuerpo_venta(_PLAN, member_id=_PLAN), "member_id"),
    (
        cuerpo_venta(_PLAN, first_payment={"amount_cop": "120000", "method": "cash"}),
        "first_payment.amount_cop",
    ),
    (
        cuerpo_venta(_PLAN, first_payment={"amount_cop": 120_000, "method": "tarjeta"}),
        "first_payment.method",
    ),
    (
        cuerpo_venta(
            _PLAN,
            first_payment={
                "amount_cop": 120_000,
                "method": "cash",
                "paid_at": "2026-10-21T10:00:00",
            },
        ),
        "first_payment.paid_at",
    ),
]


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    _INVALIDOS,
    ids=[
        "sin-plan",
        "plan-no-uuid",
        "fecha-imposible",
        "fecha-mal-formada",
        "renew-texto",
        "precio-pactado",
        "campo-desconocido",
        "primer-pago-monto-texto",
        "primer-pago-medio-ajeno",
        "primer-pago-sin-zona",
    ],
)
async def test_entrada_mal_formada_da_422_con_field_y_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    socio = await make_member(session)
    socio_id = socio.id  # tras el 422 la sesión revierte y el ORM expira (MissingGreenlet)
    r = await app_http.post(ruta_venta(socio_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["field"] == campo
    assert await membresias_del_socio(session, socio_id) == []


async def test_con_primer_pago_completo_da_201_active_con_el_pago(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    cuerpo = cuerpo_venta(plan.id, first_payment={"amount_cop": 120_000, "method": "cash"})
    r = await app_http.post(ruta_venta(socio.id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_SELL
    assert (datos["status"], datos["paid_cop"]) == ("active", 120_000)
    assert type(datos["paid_cop"]) is int
    assert datos["first_payment_id"] is not None
    assert "no-store" in r.headers.get("cache-control", "")


async def test_el_rol_del_principal_decide_la_retroactividad_del_primer_pago(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    admin = await usuario_real("admin")
    socio = await make_member(session)
    plan = await make_plan(session)
    socio_id, plan_id = socio.id, plan.id  # tras el 422 la sesión revierte y el ORM expira
    pago = {"amount_cop": 120_000, "method": "cash", "paid_at": "2026-10-13T15:00:00Z"}
    cuerpo = cuerpo_venta(plan_id, first_payment=pago)
    r = await app_http.post(ruta_venta(socio_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("paid_at_too_retroactive", "first_payment.paid_at")
    assert await membresias_del_socio(session, socio_id) == []
    r = await app_http.post(ruta_venta(socio_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active"


async def test_un_primer_pago_mayor_al_precio_sin_confirmar_da_409_en_su_campo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    socio = await make_member(session)
    plan = await make_plan(session)
    socio_id, plan_id = socio.id, plan.id
    pago = {"amount_cop": 120_001, "method": "cash"}
    r = await app_http.post(
        ruta_venta(socio_id),
        json=cuerpo_venta(plan_id, first_payment=pago),
        headers=cabeceras(coach),
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == (
        "payment_exceeds_balance",
        "first_payment.amount_cop",
    )
    assert await membresias_del_socio(session, socio_id) == []
    r = await app_http.post(
        ruta_venta(socio_id),
        json=cuerpo_venta(plan_id, first_payment={**pago, "confirm_overpayment": True}),
        headers=cabeceras(coach),
    )
    assert r.status_code == 201, r.text
    assert (r.json()["status"], r.json()["paid_cop"]) == ("active", 120_001)


async def test_member_id_de_la_ruta_no_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_venta("socio-1"), json=cuerpo_venta(_PLAN), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


async def test_la_venta_31_del_mismo_usuario_en_un_minuto_da_429_y_otro_usuario_pasa(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id  # tras cada 404 la sesión revierte y el ORM expira
    inexistente = ruta_venta(uuid4())
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(inexistente, json=cuerpo_venta(plan_id), headers=cabeceras(coach))
        assert r.status_code == 404, r.text
    r = await app_http.post(inexistente, json=cuerpo_venta(plan_id), headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(inexistente, json=cuerpo_venta(plan_id), headers=cabeceras(otro))
    assert r.status_code == 404, r.text


async def test_la_venta_con_primer_pago_tambien_cuenta_en_payments_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """Revisión de seguridad de B4 (MEDIUM-1, H-2): el primer pago de una venta es un pago y
    gasta también la cubeta `payments-write`. Con esa cubeta agotada por 30 pagos, la venta con
    pago da 429 y la venta sin pago sigue (404: el socio no existe)."""
    coach = await usuario_real("coach")
    plan = await make_plan(session)
    plan_id = plan.id  # tras cada 404 la sesión revierte y el ORM expira
    pago_inexistente = f"/api/v1/memberships/{uuid4()}/payments"
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(
            pago_inexistente,
            json={"amount_cop": 60_000, "method": "cash"},
            headers=cabeceras(coach),
        )
        assert r.status_code == 404, r.text
    con_pago = cuerpo_venta(plan_id, first_payment={"amount_cop": 120_000, "method": "cash"})
    r = await app_http.post(ruta_venta(uuid4()), json=con_pago, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    r = await app_http.post(
        ruta_venta(uuid4()), json=cuerpo_venta(plan_id), headers=cabeceras(coach)
    )
    assert r.status_code == 404, r.text


async def test_el_openapi_de_la_ruta_declara_sus_errores(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][RUTA_OPENAPI]["post"]
    assert set(operacion["responses"]) == {
        "201",
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
        "500",
        "503",
    }
    assert operacion["tags"] == ["memberships"]
