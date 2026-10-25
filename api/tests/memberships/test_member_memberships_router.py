"""`GET /api/v1/members/{member_id}/memberships` por HTTP (S3-B11, US-093; D27, D28; condición 3).

La ruta vive en el router de `memberships` con el path completo (D28: `members` no depende de
`memberships`). Contrato:
- admin y coach: 200 `{items, total, limit, offset}` (25 por defecto) con filas `MembershipOut`
  (claves exactas, con congelaciones) en orden `start_date DESC, id`, anuladas incluidas, y
  `Cache-Control: no-store`; `q` filtra por nombre de plan;
- un socio dado de baja: 200 con las suyas; uno inexistente: 404 `member_not_found`;
- 422 `validation_error` con `field`: `limit` 0 y 201, `offset` -1, `member_id` que no es UUID y
  `q` de 101 caracteres o con un carácter de control;
- `member` 403 `forbidden`; sin token 401 `unauthorized`;
- sin 429: `q` no busca personas (no usa `members.search_ids`), así que no gasta la cubeta
  compartida de búsquedas (`PII_SEARCH_BUCKET`, 60 por minuto): 61 búsquedas seguidas dan 200 y
  la cubeta queda entera para `GET /members?q=`. El OpenAPI no declara 429.

"Hoy" es 2026-10-21 (`reloj` de `api_prueba`), `expiring_days` 7.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.memberships._apoyo import CAMPOS_FREEZE, CAMPOS_MEMBERSHIP

RUTA_OPENAPI = "/api/v1/members/{member_id}/memberships"
LIMITE_DE_BUSQUEDAS = 60


def ruta(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/memberships"


async def _ficha(session: AsyncSession) -> dict[str, UUID]:
    """Lucía: una "Mensual" `active` del 2026-09-25 al 2026-10-25 (por vencer, con un pago de
    50.000 y una congelación pasada del 1 al 2 de octubre), una "Trimestral" anulada del
    2026-07-01 al 2026-09-28 y una "Mensual" `active` vieja del 2026-06-01 al 2026-06-30
    (vencida). Ana (dada de baja) tiene una "Mensual" `pending_payment` de hoy."""
    mensual = await make_plan(session)
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    lucia = await make_member(session)
    ana = await make_member(
        session,
        first_name="Ana",
        last_name="Ruiz",
        document=unique_document(),
        phone=None,
        email=None,
        deleted_at=T0 - timedelta(days=1),
    )
    vigente = await make_membership(
        session, lucia, mensual, status="active", start=date(2026, 9, 25), end=date(2026, 10, 25)
    )
    await make_freeze(session, vigente, date(2026, 10, 1), date(2026, 10, 2))
    await make_payment(session, vigente, amount=50_000)
    anulada = await make_membership(
        session,
        lucia,
        trimestral,
        status="cancelled",
        start=date(2026, 7, 1),
        end=date(2026, 9, 28),
    )
    vieja = await make_membership(
        session, lucia, mensual, status="active", start=date(2026, 6, 1), end=date(2026, 6, 30)
    )
    de_ana = await make_membership(session, ana, mensual)
    return {
        "lucia": lucia.id,
        "ana": ana.id,
        "vigente": vigente.id,
        "anulada": anulada.id,
        "vieja": vieja.id,
        "de_ana": de_ana.id,
    }


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_pagina_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    ids = await _ficha(session)
    quien = await usuario_real(rol)
    r = await app_http.get(ruta(ids["lucia"]), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["total"], datos["limit"], datos["offset"]) == (3, 25, 0)
    assert [f["id"] for f in datos["items"]] == [
        str(ids["vigente"]),
        str(ids["anulada"]),
        str(ids["vieja"]),
    ]
    assert all(set(f) == CAMPOS_MEMBERSHIP for f in datos["items"])
    vigente, anulada, vieja = datos["items"]
    assert (vigente["status"], vigente["paid_cop"], vigente["plan_name"]) == (
        "expiring",
        50_000,
        "Mensual",
    )
    assert [(z["frozen_from"], z["frozen_to"], z["days"]) for z in vigente["freezes"]] == [
        ("2026-10-01", "2026-10-02", 2)
    ]
    assert set(vigente["freezes"][0]) == CAMPOS_FREEZE
    assert (anulada["status"], anulada["plan_name"]) == ("cancelled", "Trimestral")
    assert anulada["cancel_reason"] is not None
    assert vieja["status"] == "expired"
    assert {f["member_name"] for f in datos["items"]} == {"Lucía Gómez"}


async def test_pagina_con_limit_y_offset(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _ficha(session)
    coach = await usuario_real("coach")
    r = await app_http.get(
        ruta(ids["lucia"]), params={"limit": 1, "offset": 1}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert (datos["total"], datos["limit"], datos["offset"]) == (3, 1, 1)
    assert [f["id"] for f in datos["items"]] == [str(ids["anulada"])]


async def test_limit_200_es_valido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _ficha(session)
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(ids["lucia"]), params={"limit": 200}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200


async def test_q_filtra_por_nombre_de_plan(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _ficha(session)
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(ids["lucia"]), params={"q": "TRIMESTRAL"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids["anulada"])]
    r = await app_http.get(ruta(ids["lucia"]), params={"q": "Zzyzx"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert (r.json()["items"], r.json()["total"]) == ([], 0)


async def test_un_socio_dado_de_baja_devuelve_las_suyas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _ficha(session)
    admin = await usuario_real("admin")
    r = await app_http.get(ruta(ids["ana"]), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids["de_ana"])]
    assert r.json()["items"][0]["status"] == "pending_payment"


async def test_un_socio_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"offset": -1}, "offset"),
        ({"q": "a" * 101}, "q"),
        ({"q": "men\x00sual"}, "q"),
    ],
    ids=["limit-0", "limit-201", "offset-negativo", "q-101", "q-con-nul"],
)
async def test_parametros_invalidos_dan_422_con_el_campo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    params: dict[str, Any],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(uuid4()), params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)


async def test_un_member_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(ruta(uuid4()), headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(ruta(uuid4()))
    assert sin_token.status_code == 401, sin_token.text
    assert sin_token.json()["error"]["code"] == "unauthorized"


# Sin límite por usuario (D28) --------------------------------------------------------------------


async def test_q_no_gasta_la_cubeta_de_busquedas_de_personas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """61 búsquedas por plan seguidas dan 200 y después la búsqueda de socios sigue entera."""
    ids = await _ficha(session)
    coach = await usuario_real("coach")
    destino = ruta(ids["lucia"])
    for numero in range(LIMITE_DE_BUSQUEDAS + 1):
        r = await app_http.get(destino, params={"q": "mensual"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text


async def test_el_openapi_de_la_ruta_declara_sus_errores_sin_429(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][RUTA_OPENAPI]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "404", "422", "500", "503"}
    assert operacion["tags"] == ["memberships"]
    nombres = {p["name"] for p in operacion["parameters"] if p["in"] == "query"}
    assert nombres == {"limit", "offset", "q"}
    respuesta = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert respuesta == {"$ref": "#/components/schemas/Page_MembershipOut_"}
