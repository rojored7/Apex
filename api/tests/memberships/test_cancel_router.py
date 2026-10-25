"""`POST /api/v1/memberships/{membership_id}/cancel` por HTTP (S3-B6, US-090; D17, D27, H-2, E2,
E15, M-7, S3-D42, S3-D83).

- admin: 200 `MembershipOut` con las claves exactas, la membresía anulada (motivo recortado,
  `cancelled_at` = ahora) y `Cache-Control: no-store`; coach y `member` 403 sin anular; sin token
  401;
- 422 `validation_error` con `field="reason"`: motivo ausente, vacío, de 4 caracteres y de 501
  (estos dos los decide `cancel` con `rules.normalize_cancel_reason`), con NUL y enorme (100.000
  caracteres: el esquema lo corta antes, sin eco); un campo desconocido y un `membership_id` que
  no es UUID también dan 422 con su `field`;
- 404 `membership_not_found`; 409 `membership_already_cancelled` con envelope;
- límite `admin-write` (30 por minuto por usuario, `USER_ADMIN_WRITE_LIMIT_PER_MIN`, E15),
  compartido con anular un pago (S3-B5): 20 anulaciones de pago y 10 de membresía del mismo admin
  en un minuto, y la 31 (de membresía) da 429 con `Retry-After`; otro admin pasa;
- OpenAPI de la ruta: 200, 401, 403, 404, 409, 422, 429, 500 y 503, cuerpo `CancelMembershipIn`
  (con `maxLength` 2000 en `reason`) y respuesta `MembershipOut`.

"Ahora" es `T0` = 2026-10-21T15:00:00Z (`reloj` de `api_prueba`).
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
from tests.memberships._apoyo import (
    CAMPOS_MEMBERSHIP,
    cuerpo_cancelacion,
    leer_membresia,
    ruta_cancelar,
)
from tests.payments._apoyo import cuerpo_anulacion

RUTA_OPENAPI = "/api/v1/memberships/{membership_id}/cancel"
TOPE_POR_MINUTO = 30
MOTIVO = "Cambio de ciudad"


async def _membresia(session: AsyncSession) -> UUID:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, status="active")
    return membresia.id


async def _sin_anular(session: AsyncSession, membership_id: UUID) -> bool:
    fila = await leer_membresia(session, membership_id)
    return fila is not None and fila["status"] == "active" and fila["cancel_reason"] is None


async def test_el_admin_anula_y_recibe_200_con_el_contrato(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    membresia_id = await _membresia(session)
    r = await app_http.post(
        ruta_cancelar(membresia_id),
        json=cuerpo_cancelacion(f"  {MOTIVO}  "),
        headers=cabeceras(admin),
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_MEMBERSHIP
    assert (datos["id"], datos["status"]) == (str(membresia_id), "cancelled")
    assert datos["cancel_reason"] == MOTIVO
    assert datos["cancelled_at"].startswith("2026-10-21T15:00:00")
    assert "no-store" in r.headers.get("cache-control", "")
    fila = await leer_membresia(session, membresia_id)
    assert fila is not None and fila["status"] == "cancelled" and fila["cancelled_by"] == admin.id


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403_y_no_anulan(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    membresia_id = await _membresia(session)
    r = await app_http.post(
        ruta_cancelar(membresia_id), json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(quien)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await _sin_anular(session, membresia_id)


async def test_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.post(ruta_cancelar(uuid4()), json=cuerpo_cancelacion(MOTIVO))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


# 422 ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        cuerpo_cancelacion(""),
        cuerpo_cancelacion("abcd"),
        cuerpo_cancelacion("x" * 501),
        cuerpo_cancelacion("Motivo\x00largo"),
        cuerpo_cancelacion("y" * 100_000),
    ],
    ids=["ausente", "vacio", "cuatro", "501", "nul", "enorme"],
)
async def test_un_motivo_invalido_da_422_en_reason_y_no_anula(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
) -> None:
    admin = await usuario_real("admin")
    membresia_id = await _membresia(session)
    r = await app_http.post(ruta_cancelar(membresia_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text[:300]
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "reason")
    assert "x" * 501 not in r.text and "y" * 600 not in r.text
    assert await _sin_anular(session, membresia_id)


async def test_un_campo_desconocido_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    membresia_id = await _membresia(session)
    r = await app_http.post(
        ruta_cancelar(membresia_id),
        json={**cuerpo_cancelacion(MOTIVO), "cancelled_by": str(uuid4())},
        headers=cabeceras(admin),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "cancelled_by"
    assert await _sin_anular(session, membresia_id)


async def test_un_membership_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_cancelar("membresia-1"), json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "membership_id"


# 404 y 409 ----------------------------------------------------------------------------------------


async def test_una_membresia_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_cancelar(uuid4()), json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "membership_not_found"


async def test_anular_dos_veces_da_409_con_envelope_y_no_cambia_la_fila(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    membresia_id = await _membresia(session)
    r = await app_http.post(
        ruta_cancelar(membresia_id), json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    anulada = await leer_membresia(session, membresia_id)
    r = await app_http.post(
        ruta_cancelar(membresia_id),
        json=cuerpo_cancelacion("Otro motivo distinto"),
        headers=cabeceras(admin),
    )
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    assert r.json()["error"]["code"] == "membership_already_cancelled"
    assert await leer_membresia(session, membresia_id) == anulada


# Límite por usuario (H-2, S3-D42, E15) -----------------------------------------------------------


async def test_admin_write_es_compartido_con_anular_pagos_y_la_31_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    membresia = ruta_cancelar(uuid4())
    pago = f"/api/v1/payments/{uuid4()}/void"
    for _ in range(20):
        r = await app_http.post(pago, json=cuerpo_anulacion(MOTIVO), headers=cabeceras(admin))
        assert r.status_code == 404, r.text
    for _ in range(TOPE_POR_MINUTO - 20):
        r = await app_http.post(
            membresia, json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(admin)
        )
        assert r.status_code == 404, r.text
    r = await app_http.post(membresia, json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(membresia, json=cuerpo_cancelacion(MOTIVO), headers=cabeceras(otro))
    assert r.status_code == 404, r.text


# OpenAPI (D27) ------------------------------------------------------------------------------------


async def test_el_openapi_de_la_ruta_declara_sus_errores(api_prueba: FastAPI) -> None:
    esquema = api_prueba.openapi()
    operacion = esquema["paths"][RUTA_OPENAPI]["post"]
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
    assert operacion["tags"] == ["memberships"]
    exito = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert exito["$ref"] == "#/components/schemas/MembershipOut"
    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]
    assert cuerpo["$ref"] == "#/components/schemas/CancelMembershipIn"
    motivo = esquema["components"]["schemas"]["CancelMembershipIn"]["properties"]["reason"]
    assert motivo["maxLength"] == 2000
