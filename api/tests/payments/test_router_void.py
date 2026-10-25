"""`POST /api/v1/payments/{payment_id}/void` por HTTP (S3-B5, US-097; D13, D27, H-2, E2, E15).

- admin: 200 `PaymentOut` con las claves exactas, la fila anulada (motivo recortado, `voided_by`
  del principal, `voided_at` = ahora) y `Cache-Control: no-store`; coach y `member` 403 sin
  anular; sin token 401;
- 422 `validation_error` con `field="reason"`: motivo ausente, vacío, solo espacios y de 501
  caracteres (este último lo decide `void` con `rules.normalize_void_reason`, mismo código); un
  campo desconocido y un `payment_id` que no es UUID también dan 422 con su `field`;
- 404 `payment_not_found`; 409 `payment_already_voided` con envelope (`{"error": ...}`);
- límite `admin-write` (30 por minuto por usuario, `USER_ADMIN_WRITE_LIMIT_PER_MIN`, E15, S3-D42):
  la anulación 31 del mismo admin en un minuto da 429 con `Retry-After`; otro admin pasa;
- OpenAPI de la ruta: 200, 401, 403, 404, 409, 422, 429, 500 y 503, cuerpo `VoidPaymentIn` y
  respuesta `PaymentOut`.

"Ahora" es `T0` = 2026-10-21T15:00:00Z (`reloj` de `api_prueba`). El pago es de 60.000 (fábrica)
sobre una membresía `pending_payment` de 120.000: anularlo no cambia la membresía.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payment
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import CAMPOS_PAYMENT, cuerpo_anulacion, leer_pago

RUTA_OPENAPI = "/api/v1/payments/{payment_id}/void"
TOPE_POR_MINUTO = 30
MOTIVO = "Monto mal digitado"


def ruta_anular(payment_id: UUID | str) -> str:
    return f"/api/v1/payments/{payment_id}/void"


async def _pago(session: AsyncSession) -> Payment:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan)
    return await make_payment(session, membresia, amount=60_000, reference="NEQ-1")


async def _sin_anular(session: AsyncSession, payment_id: UUID) -> bool:
    fila = await leer_pago(session, payment_id)
    return fila is not None and fila["voided"] is False


async def test_el_admin_anula_y_recibe_200_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    pago = await _pago(session)
    pago_id, membresia_id = pago.id, pago.membership_id
    r = await app_http.post(
        ruta_anular(pago_id), json=cuerpo_anulacion(f"  {MOTIVO}  "), headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_PAYMENT
    assert (datos["id"], datos["membership_id"]) == (str(pago_id), str(membresia_id))
    assert (datos["voided"], datos["void_reason"]) == (True, MOTIVO)
    assert datos["voided_by"] == str(admin.id)
    assert datos["voided_at"].startswith("2026-10-21T15:00:00")
    assert (datos["amount_cop"], datos["reference"]) == (60_000, "NEQ-1")
    assert "no-store" in r.headers.get("cache-control", "")
    fila = await leer_pago(session, pago_id)
    assert fila is not None and fila["voided"] is True and fila["voided_by"] == admin.id


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_y_no_anulan(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    pago = await _pago(session)
    pago_id = pago.id
    r = await app_http.post(
        ruta_anular(pago_id), json=cuerpo_anulacion(MOTIVO), headers=cabeceras(quien)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await _sin_anular(session, pago_id)


async def test_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.post(ruta_anular(uuid4()), json=cuerpo_anulacion(MOTIVO))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


# 422 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [{}, cuerpo_anulacion(""), cuerpo_anulacion("   "), cuerpo_anulacion("x" * 501)],
    ids=["ausente", "vacio", "espacios", "501"],
)
async def test_un_motivo_invalido_da_422_en_reason_y_no_anula(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
) -> None:
    admin = await usuario_real("admin")
    pago = await _pago(session)
    pago_id = pago.id
    r = await app_http.post(ruta_anular(pago_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "reason")
    assert "x" * 501 not in r.text
    assert await _sin_anular(session, pago_id)


async def test_un_campo_desconocido_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    pago = await _pago(session)
    pago_id = pago.id
    r = await app_http.post(
        ruta_anular(pago_id),
        json={**cuerpo_anulacion(MOTIVO), "voided_by": str(uuid4())},
        headers=cabeceras(admin),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "voided_by"
    assert await _sin_anular(session, pago_id)


async def test_un_payment_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_anular("pago-1"), json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "payment_id"


# 404 y 409 ----------------------------------------------------------------------------------------


async def test_un_pago_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_anular(uuid4()), json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "payment_not_found"


async def test_anular_dos_veces_da_409_con_envelope_y_no_cambia_la_fila(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    pago = await _pago(session)
    pago_id = pago.id
    r = await app_http.post(
        ruta_anular(pago_id), json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    anulada = await leer_pago(session, pago_id)
    r = await app_http.post(
        ruta_anular(pago_id), json=cuerpo_anulacion("Otro motivo"), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "payment_already_voided"
    assert await leer_pago(session, pago_id) == anulada


# Límite por usuario (H-2, S3-D42, E15) -----------------------------------------------------------


async def test_la_anulacion_31_del_mismo_admin_en_un_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    inexistente = ruta_anular(uuid4())
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(
            inexistente, json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin)
        )
        assert r.status_code == 404, r.text
    r = await app_http.post(inexistente, json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(inexistente, json=cuerpo_anulacion(MOTIVO), headers=cabeceras(otro))
    assert r.status_code == 404, r.text


# OpenAPI (D27) ------------------------------------------------------------------------------------


async def test_el_openapi_de_la_ruta_declara_sus_errores(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][RUTA_OPENAPI]["post"]
    assert set(operacion["responses"]) == {
        "200",
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
    exito = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert exito["$ref"] == "#/components/schemas/PaymentOut"
    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]
    assert cuerpo["$ref"] == "#/components/schemas/VoidPaymentIn"


async def test_un_motivo_enorme_se_corta_en_el_esquema_con_422_en_reason(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """Revisión de seguridad de B5 (LOW-2): 100.000 caracteres no llegan a NFC ni al service; el
    esquema los corta antes (`VOID_REASON_INPUT_MAX`) con el mismo 422 y sin eco."""
    admin = await usuario_real("admin")
    pago = await _pago(session)
    pago_id = pago.id
    enorme = "y" * 100_000
    r = await app_http.post(
        ruta_anular(pago_id), json=cuerpo_anulacion(enorme), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text[:200]
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "reason")
    assert "y" * 600 not in r.text
    assert await _sin_anular(session, pago_id)
