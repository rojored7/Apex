"""`POST /api/v1/memberships/{membership_id}/payments` por HTTP (S3-B4, US-095; E9, S3-D77; H-1,
H-2, M-8, D27).

La ruta nace en B4 con el gate REAL (`memberships.service.membership_payability`, registrado al
importarse `memberships.service`): estas pruebas no usan `gate_doble` (D1, riesgo 5 del sprint).

- admin y coach: 201 `PaymentOut` con las claves exactas, montos enteros JSON, `registered_by` del
  principal y `Cache-Control: no-store`; `member` 403; sin token 401;
- `role` sale del principal (nota de B3 para B4): el coach con `paid_at` de hace 8 días recibe 422
  `paid_at_too_retroactive` (`field="paid_at"`) y el admin registra el mismo pago; un `role` en el
  cuerpo es un campo desconocido (422);
- 422 de forma con `field`: `amount_cop` (texto, cero, decimal), `method` (`tarjeta`),
  `reference` (fuera del patrón de comprobante, M-7), `paid_at` (sin zona) y `membership_id` de la
  ruta no UUID; 422 semántico de `paid_at` futuro (`validation_error`, `field="paid_at"`);
- 404 `membership_not_found`; 409 con envelope: `payment_exceeds_balance` (`field="amount_cop"`),
  `payment_possible_duplicate` y `membership_cancelled` (la cancelada sale de la fábrica: la ruta
  de anular llega en B6); `confirm_overpayment` y `confirm_duplicate` viajan en el cuerpo;
- límite `payments-write` (30 por minuto por usuario, `USER_WRITE_LIMIT_PER_MIN`, S3-D42): el pago
  31 del mismo usuario en un minuto da 429 con `Retry-After`; otro usuario pasa y la cubeta es
  distinta de `memberships-write` (el mismo coach todavía puede vender);
- OpenAPI de la ruta: 201, 401, 403, 404, 409, 422, 429, 500 y 503, cuerpo `PaymentIn` y respuesta
  `PaymentOut`.

"Ahora" es `T0` = 2026-10-21T15:00:00Z (`reloj` de `api_prueba`). La membresía es la venta del
plan "Mensual" de 120.000 (`make_membership`, `pending_payment`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memberships.models import Membership
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import cuerpo_venta, leer_membresia, ruta_venta
from tests.payments._apoyo import CAMPOS_PAYMENT, cuerpo_pago, pagos_de

RUTA_OPENAPI = "/api/v1/memberships/{membership_id}/payments"
TOPE_POR_MINUTO = 30


def ruta_pago(membership_id: UUID | str) -> str:
    return f"/api/v1/memberships/{membership_id}/payments"


async def _membresia(session: AsyncSession, **cambios: Any) -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, **cambios)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_registran_y_reciben_201_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    membresia = await _membresia(session)
    membresia_id, socio_id = membresia.id, membresia.member_id
    r = await app_http.post(
        ruta_pago(membresia_id),
        json=cuerpo_pago(method="nequi", reference="NEQ-00123"),
        headers=cabeceras(quien),
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_PAYMENT
    assert (datos["membership_id"], datos["member_id"]) == (str(membresia_id), str(socio_id))
    assert datos["amount_cop"] == 60_000 and type(datos["amount_cop"]) is int
    assert '"amount_cop":60000,' in r.text.replace(" ", "")
    assert (datos["method"], datos["reference"]) == ("nequi", "NEQ-00123")
    assert datos["registered_by"] == str(quien.id)
    assert datos["voided"] is False
    assert (datos["void_reason"], datos["voided_by"], datos["voided_at"]) == (None, None, None)
    assert "no-store" in r.headers.get("cache-control", "")
    filas = await pagos_de(session, membresia_id)
    assert [f["id"] for f in filas] == [UUID(datos["id"])]
    assert (filas[0]["registered_by"], filas[0]["created_by"]) == (quien.id, quien.id)


async def test_member_recibe_403_y_no_se_registra_nada(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    socio_usuario = await usuario_real("member")
    membresia = await _membresia(session)
    membresia_id = membresia.id  # tras un error la sesión revierte y el ORM expira
    r = await app_http.post(
        ruta_pago(membresia_id), json=cuerpo_pago(), headers=cabeceras(socio_usuario)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await pagos_de(session, membresia_id) == []


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    r = await app_http.post(ruta_pago(uuid4()), json=cuerpo_pago())
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


# El rol sale del principal (M-8; nota de B3 para B4) ----------------------------------------------

HACE_8_DIAS = "2026-10-13T15:00:00Z"


async def test_el_coach_no_registra_8_dias_atras_y_el_admin_si(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    admin = await usuario_real("admin")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    cuerpo = cuerpo_pago(paid_at=HACE_8_DIAS)
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("paid_at_too_retroactive", "paid_at")
    assert await pagos_de(session, membresia_id) == []
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.json()["paid_at"].startswith("2026-10-13T15:00:00")


async def test_un_role_en_el_cuerpo_es_un_campo_desconocido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    r = await app_http.post(
        ruta_pago(membresia_id),
        json=cuerpo_pago(paid_at=HACE_8_DIAS, role="admin"),
        headers=cabeceras(coach),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "role"
    assert await pagos_de(session, membresia_id) == []


# 422 de forma y semántico -------------------------------------------------------------------------

_INVALIDOS: list[tuple[dict[str, Any], str]] = [
    (cuerpo_pago(amount_cop="60000"), "amount_cop"),
    (cuerpo_pago(amount_cop=0), "amount_cop"),
    (cuerpo_pago(amount_cop=60_000.5), "amount_cop"),
    (cuerpo_pago(method="tarjeta"), "method"),
    (cuerpo_pago(reference="mi correo a@b.co"), "reference"),
    (cuerpo_pago(paid_at="2026-10-21T10:00:00"), "paid_at"),
    (cuerpo_pago(confirm_overpayment="yes"), "confirm_overpayment"),
    ({"method": "cash"}, "amount_cop"),
]


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    _INVALIDOS,
    ids=[
        "monto-texto",
        "monto-cero",
        "monto-decimal",
        "medio-ajeno",
        "referencia-fuera-del-patron",
        "paid-at-sin-zona",
        "confirmacion-no-booleana",
        "sin-monto",
    ],
)
async def test_entrada_mal_formada_da_422_con_field_y_no_registra_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["field"] == campo
    assert await pagos_de(session, membresia_id) == []


async def test_paid_at_futuro_da_422_validation_error_en_paid_at(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    r = await app_http.post(
        ruta_pago(membresia_id),
        json=cuerpo_pago(paid_at="2026-10-21T15:05:01Z"),
        headers=cabeceras(admin),
    )
    assert r.status_code == 422, r.text
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == (
        "validation_error",
        "paid_at",
    )
    assert await pagos_de(session, membresia_id) == []


async def test_membership_id_de_la_ruta_no_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(ruta_pago("membresia-1"), json=cuerpo_pago(), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "membership_id"


# 404 y 409 ----------------------------------------------------------------------------------------


async def test_membresia_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(ruta_pago(uuid4()), json=cuerpo_pago(), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "membership_not_found"
    assert set(r.json()) == {"error"}


async def test_un_peso_sobre_el_saldo_da_409_y_con_confirmacion_201(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    r = await app_http.post(
        ruta_pago(membresia_id), json=cuerpo_pago(amount_cop=120_001), headers=cabeceras(coach)
    )
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("payment_exceeds_balance", "amount_cop")
    assert await pagos_de(session, membresia_id) == []
    r = await app_http.post(
        ruta_pago(membresia_id),
        json=cuerpo_pago(amount_cop=120_001, confirm_overpayment=True),
        headers=cabeceras(coach),
    )
    assert r.status_code == 201, r.text
    assert "confirm_overpayment" not in r.json()
    assert len(await pagos_de(session, membresia_id)) == 1


async def test_el_mismo_pago_repetido_da_409_y_con_confirmacion_201(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    membresia = await _membresia(session, price=1_000_000)
    membresia_id = membresia.id
    cuerpo = cuerpo_pago(amount_cop=30_000, reference="REC-1")
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 201, r.text
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "payment_possible_duplicate"
    assert len(await pagos_de(session, membresia_id)) == 1
    r = await app_http.post(
        ruta_pago(membresia_id),
        json={**cuerpo, "confirm_duplicate": True},
        headers=cabeceras(coach),
    )
    assert r.status_code == 201, r.text
    assert len(await pagos_de(session, membresia_id)) == 2


async def test_una_membresia_cancelada_da_409_membership_cancelled(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    membresia = await _membresia(session, status="cancelled")
    membresia_id = membresia.id
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo_pago(), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "membership_cancelled"
    assert await pagos_de(session, membresia_id) == []


async def test_el_pago_que_cubre_activa_la_membresia_por_http(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """Demo 2 (blueprint 6.2): 60.000 ya pagados (fábrica) más 60.000 por la ruta cubren 120.000:
    el handler real de `PaymentRegistered` deja la membresía `active` en la misma petición."""
    coach = await usuario_real("coach")
    membresia = await _membresia(session)
    membresia_id = membresia.id
    await make_payment(session, membresia, amount=60_000)
    r = await app_http.post(ruta_pago(membresia_id), json=cuerpo_pago(), headers=cabeceras(coach))
    assert r.status_code == 201, r.text
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and fila["status"] == "active"


# Límite por usuario (H-2, S3-D42) ---------------------------------------------------------------


async def test_el_pago_31_del_mismo_usuario_en_un_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id  # tras cada 404 la sesión revierte y el ORM expira
    inexistente = ruta_pago(uuid4())
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(inexistente, json=cuerpo_pago(), headers=cabeceras(coach))
        assert r.status_code == 404, r.text
    r = await app_http.post(inexistente, json=cuerpo_pago(), headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(inexistente, json=cuerpo_pago(), headers=cabeceras(otro))
    assert r.status_code == 404, r.text
    r = await app_http.post(
        ruta_venta(uuid4()), json=cuerpo_venta(plan_id), headers=cabeceras(coach)
    )
    assert r.status_code == 404, r.text  # `memberships-write` es otra cubeta


# OpenAPI (D27) ------------------------------------------------------------------------------------


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
    assert operacion["tags"] == ["payments"]
    exito = operacion["responses"]["201"]["content"]["application/json"]["schema"]
    assert exito["$ref"] == "#/components/schemas/PaymentOut"
    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]
    assert cuerpo["$ref"] == "#/components/schemas/PaymentIn"
