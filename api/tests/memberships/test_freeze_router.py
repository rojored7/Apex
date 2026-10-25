"""`POST /api/v1/memberships/{membership_id}/freeze` por HTTP (S3-B2, US-089; blueprint B2 "Rojo";
D14, Q7, H-2, S3-D42, D27).

"Hoy" es 2026-10-21. La membresía base es `active` del 1 al 31 de octubre; congelar del 21 al 30
(10 días) deja `frozen` y el fin en el 2026-11-10.

- admin y coach (Q7): 200 `MembershipOut` con las claves exactas, la congelación con las claves de
  `FreezeOut` y `Cache-Control: no-store`; `member` 403; sin token 401; 404
  `membership_not_found`;
- 422 de forma con `field` (fechas ausentes o mal formadas, `reason` u otro campo desconocido, id
  de la ruta no UUID) y 422 de la regla (D14): `validation_error` con `field="frozen_to"` (fechas
  invertidas), `freeze_too_retroactive` y `freeze_outside_validity` con `field="frozen_from"`;
- 409 con envelope por cada código de estado: `membership_not_freezable`,
  `freeze_already_scheduled`, `freeze_limit_reached`, `freeze_days_exceeded` y
  `overlaps_future_membership` (con `existing_id`); nada cambia;
- límite `memberships-write` compartido con la venta (S3-D42): 20 ventas y 10 congelaciones del
  mismo usuario dan 404 y la congelación 31 da 429 con `Retry-After`; otro usuario pasa;
- OpenAPI de la ruta: 200, 401, 403, 404, 409, 422, 429, 500 y 503.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memberships.models import Membership
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    CAMPOS_FREEZE,
    CAMPOS_MEMBERSHIP,
    congelaciones_de,
    cuerpo_congelacion,
    cuerpo_venta,
    leer_membresia,
    ruta_congelar,
    ruta_venta,
)

RUTA_OPENAPI = "/api/v1/memberships/{membership_id}/freeze"
HOY = date(2026, 10, 21)
INICIO = date(2026, 10, 1)
FIN = date(2026, 10, 31)
TOPE_POR_MINUTO = 30
VENTAS_ANTES = 20


async def _activa(session: AsyncSession, **cambios: Any) -> Membership:
    socio = await make_member(session)
    plan = await make_plan(session)
    return await make_membership(session, socio, plan, status="active", start=INICIO, **cambios)


async def _sin_cambios(session: AsyncSession, membership_id: UUID) -> bool:
    fila = await leer_membresia(session, membership_id)
    return fila is not None and (fila["status"], fila["end_date"]) == ("active", FIN)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_congelan_y_reciben_200_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    membresia = await _activa(session)
    r = await app_http.post(
        ruta_congelar(membresia.id),
        json=cuerpo_congelacion(HOY, date(2026, 10, 30)),
        headers=cabeceras(quien),
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_MEMBERSHIP
    assert datos["id"] == str(membresia.id)
    assert datos["status"] == "frozen"
    assert (datos["start_date"], datos["end_date"]) == ("2026-10-01", "2026-11-10")
    assert datos["agreed_price_cop"] == 120_000 and type(datos["paid_cop"]) is int
    assert len(datos["freezes"]) == 1
    congelacion = datos["freezes"][0]
    assert set(congelacion) == CAMPOS_FREEZE
    assert (congelacion["frozen_from"], congelacion["frozen_to"]) == ("2026-10-21", "2026-10-30")
    assert congelacion["days"] == 10 and type(congelacion["days"]) is int
    assert "no-store" in r.headers.get("cache-control", "")
    filas = await congelaciones_de(session, membresia.id)
    assert [str(f["id"]) for f in filas] == [congelacion["id"]]
    assert filas[0]["created_by"] == quien.id


async def test_member_recibe_403_y_no_se_congela(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    socio_usuario = await usuario_real("member")
    membresia = await _activa(session)
    membresia_id = membresia.id  # tras un error la sesión revierte y el ORM expira
    r = await app_http.post(
        ruta_congelar(membresia_id),
        json=cuerpo_congelacion(HOY, HOY),
        headers=cabeceras(socio_usuario),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await congelaciones_de(session, membresia_id) == []
    assert await _sin_cambios(session, membresia_id)


async def test_sin_token_da_401(app_http: AsyncClient, session: AsyncSession) -> None:
    r = await app_http.post(ruta_congelar(uuid4()), json=cuerpo_congelacion(HOY, HOY))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_membresia_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_congelar(uuid4()), json=cuerpo_congelacion(HOY, HOY), headers=cabeceras(admin)
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "membership_not_found"


# 422 ----------------------------------------------------------------------------------------------

_INVALIDOS: list[tuple[dict[str, Any], str]] = [
    ({"frozen_to": "2026-10-21"}, "frozen_from"),
    ({"frozen_from": "2026-10-21"}, "frozen_to"),
    (cuerpo_congelacion("2026-13-01", "2026-10-21"), "frozen_from"),
    (cuerpo_congelacion("2026-10-21", "21/10/2026"), "frozen_to"),
    (cuerpo_congelacion("2026-10-21", "2026-10-21", reason="Viaje"), "reason"),
    (cuerpo_congelacion("2026-10-21", "2026-10-21", days=1), "days"),
]


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    _INVALIDOS,
    ids=["sin-desde", "sin-hasta", "fecha-imposible", "fecha-mal-formada", "motivo", "dias"],
)
async def test_entrada_mal_formada_da_422_con_field_y_no_congela(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cuerpo: dict[str, Any],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    membresia = await _activa(session)
    membresia_id = membresia.id
    r = await app_http.post(ruta_congelar(membresia_id), json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert await congelaciones_de(session, membresia_id) == []


async def test_membership_id_de_la_ruta_no_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        ruta_congelar("membresia-1"), json=cuerpo_congelacion(HOY, HOY), headers=cabeceras(admin)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "membership_id"


@pytest.mark.parametrize(
    ("desde", "hasta", "codigo", "campo"),
    [
        (date(2026, 10, 25), date(2026, 10, 24), "validation_error", "frozen_to"),
        (date(2026, 10, 13), date(2026, 10, 20), "freeze_too_retroactive", "frozen_from"),
        (date(2026, 11, 1), date(2026, 11, 2), "freeze_outside_validity", "frozen_from"),
    ],
    ids=["fechas-invertidas", "demasiado-retroactiva", "fuera-de-vigencia"],
)
async def test_las_reglas_de_forma_dan_422_con_codigo_y_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    desde: date,
    hasta: date,
    codigo: str,
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    membresia = await _activa(session)
    membresia_id = membresia.id
    r = await app_http.post(
        ruta_congelar(membresia_id), json=cuerpo_congelacion(desde, hasta), headers=cabeceras(coach)
    )
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == (codigo, campo)
    assert await congelaciones_de(session, membresia_id) == []
    assert await _sin_cambios(session, membresia_id)


# 409 ----------------------------------------------------------------------------------------------


async def _pendiente(session: AsyncSession) -> tuple[UUID, UUID | None]:
    socio = await make_member(session)
    plan = await make_plan(session)
    membresia = await make_membership(session, socio, plan, start=INICIO)
    return membresia.id, None


async def _programada(session: AsyncSession) -> tuple[UUID, UUID | None]:
    membresia = await _activa(session)
    await make_freeze(session, membresia, date(2026, 10, 25), date(2026, 10, 27))
    return membresia.id, None


async def _dos_usadas(session: AsyncSession) -> tuple[UUID, UUID | None]:
    membresia = await _activa(session)
    await make_freeze(session, membresia, date(2026, 10, 1), date(2026, 10, 2))
    await make_freeze(session, membresia, date(2026, 10, 5), date(2026, 10, 6))
    return membresia.id, None


async def _activa_sola(session: AsyncSession) -> tuple[UUID, UUID | None]:
    return (await _activa(session)).id, None


async def _con_futura(session: AsyncSession) -> tuple[UUID, UUID | None]:
    socio = await make_member(session)
    plan = await make_plan(session)
    actual = await make_membership(session, socio, plan, status="active", start=INICIO)
    futura = await make_membership(session, socio, plan, start=date(2026, 11, 1))
    return actual.id, futura.id


@pytest.mark.parametrize(
    ("preparar", "hasta", "codigo"),
    [
        (_pendiente, HOY, "membership_not_freezable"),
        (_programada, HOY, "freeze_already_scheduled"),
        (_dos_usadas, HOY, "freeze_limit_reached"),
        (_activa_sola, date(2026, 11, 20), "freeze_days_exceeded"),
        (_con_futura, date(2026, 10, 30), "overlaps_future_membership"),
    ],
    ids=["pendiente", "ya-programada", "tope-de-veces", "tope-de-dias", "choca-con-futura"],
)
async def test_cada_rechazo_por_estado_da_409_con_envelope(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    preparar: Any,
    hasta: date,
    codigo: str,
) -> None:
    admin = await usuario_real("admin")
    membresia_id, existente = await preparar(session)
    antes = await congelaciones_de(session, membresia_id)
    r = await app_http.post(
        ruta_congelar(membresia_id), json=cuerpo_congelacion(HOY, hasta), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    assert set(r.json()) == {"error"}
    error = r.json()["error"]
    assert error["code"] == codigo
    assert error.get("existing_id") == (str(existente) if existente else None)
    assert await congelaciones_de(session, membresia_id) == antes


# Límite por usuario (H-2, S3-D42) ---------------------------------------------------------------


async def test_ventas_y_congelaciones_comparten_la_cubeta_y_la_31_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("admin")
    plan = await make_plan(session)
    plan_id = plan.id  # tras cada 404 la sesión revierte y el ORM expira
    for _ in range(VENTAS_ANTES):
        r = await app_http.post(
            ruta_venta(uuid4()), json=cuerpo_venta(plan_id), headers=cabeceras(coach)
        )
        assert r.status_code == 404, r.text
    inexistente = ruta_congelar(uuid4())
    for _ in range(TOPE_POR_MINUTO - VENTAS_ANTES):
        r = await app_http.post(
            inexistente, json=cuerpo_congelacion(HOY, HOY), headers=cabeceras(coach)
        )
        assert r.status_code == 404, r.text
    r = await app_http.post(
        inexistente, json=cuerpo_congelacion(HOY, HOY), headers=cabeceras(coach)
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await app_http.post(inexistente, json=cuerpo_congelacion(HOY, HOY), headers=cabeceras(otro))
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
    assert operacion["tags"] == ["memberships"]
    exito = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert exito["$ref"] == "#/components/schemas/MembershipOut"
    cuerpo = operacion["requestBody"]["content"]["application/json"]["schema"]
    assert cuerpo["$ref"] == "#/components/schemas/FreezeIn"


async def test_el_esquema_de_freeze_out_tiene_id_y_created_at(api_prueba: FastAPI) -> None:
    esquemas = api_prueba.openapi()["components"]["schemas"]
    assert set(esquemas["FreezeOut"]["properties"]) == CAMPOS_FREEZE
    assert set(esquemas["FreezeIn"]["properties"]) == {"frozen_from", "frozen_to"}
