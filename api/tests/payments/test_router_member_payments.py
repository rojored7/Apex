"""`GET /api/v1/members/{member_id}/payments` por HTTP (S3-B11, US-101; D26, D27, D28, M-8).

La ruta vive en el router de `payments` con el path completo (D28: `members` no depende de
`payments`). Contrato:
- admin y coach: 200 `{items, total, limit, offset}` (25 por defecto) con filas `PaymentRow`
  (claves exactas, `backdated` incluido) en orden `paid_at DESC, id DESC` y
  `Cache-Control: no-store`; `voided` opcional (`true`/`false`); `q` es la referencia exacta;
- un socio dado de baja: 200 con los suyos; uno inexistente: 404 `member_not_found`;
- 422 `validation_error` con `field`: `limit` 0 y 201, `offset` -1, `voided` que no es booleano,
  `member_id` que no es UUID y `q` de 101 caracteres;
- `member` 403 `forbidden`; sin token 401 `unauthorized`;
- sin 429 (no busca personas): 61 búsquedas seguidas dan 200 y la cubeta compartida queda entera.

"Hoy" es 2026-10-21 (`reloj` de `api_prueba`). Datos (`_pagos`): Lucía Gómez con una "Mensual"
`active` y tres pagos: 60.000 en efectivo el 2026-10-10T15:00Z (vigente), 40.000 por Nequi el
2026-10-05T15:00Z con referencia `NEQ-55` registrado 72 h después (`backdated`) y 20.000 en
efectivo el 2026-10-03T15:00Z anulado. Ana Ruiz (dada de baja) tiene uno de 90.000.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.payments._apoyo import CAMPOS_ROW

RUTA_OPENAPI = "/api/v1/members/{member_id}/payments"
LIMITE_DE_BUSQUEDAS = 60


def ruta(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/payments"


async def _pagos(session: AsyncSession) -> dict[str, UUID]:
    plan = await make_plan(session)
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
    membresia = await make_membership(session, lucia, plan, status="active")
    de_ana = await make_membership(session, ana, plan, status="active")
    vigente_pagado = datetime(2026, 10, 10, 15, tzinfo=UTC)
    retro_pagado = datetime(2026, 10, 5, 15, tzinfo=UTC)
    anulado_pagado = datetime(2026, 10, 3, 15, tzinfo=UTC)
    vigente = await make_payment(
        session,
        membresia,
        amount=60_000,
        paid_at=vigente_pagado,
        created_at=vigente_pagado + timedelta(hours=1),
    )
    retro = await make_payment(
        session,
        membresia,
        amount=40_000,
        method="nequi",
        reference="NEQ-55",
        paid_at=retro_pagado,
        created_at=retro_pagado + timedelta(hours=72),
    )
    anulado = await make_payment(
        session,
        membresia,
        amount=20_000,
        paid_at=anulado_pagado,
        voided=True,
        created_at=anulado_pagado + timedelta(hours=1),
    )
    de_ana_pago = await make_payment(
        session,
        de_ana,
        amount=90_000,
        paid_at=vigente_pagado,
        created_at=vigente_pagado + timedelta(hours=1),
    )
    return {
        "lucia": lucia.id,
        "ana": ana.id,
        "vigente": vigente.id,
        "retro": retro.id,
        "anulado": anulado.id,
        "de_ana": de_ana_pago.id,
    }


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_pagina_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    ids = await _pagos(session)
    quien = await usuario_real(rol)
    r = await app_http.get(ruta(ids["lucia"]), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["total"], datos["limit"], datos["offset"]) == (3, 25, 0)
    assert [f["id"] for f in datos["items"]] == [
        str(ids["vigente"]),
        str(ids["retro"]),
        str(ids["anulado"]),
    ]
    assert all(set(f) == CAMPOS_ROW for f in datos["items"])
    assert [f["backdated"] for f in datos["items"]] == [False, True, False]
    assert [f["voided"] for f in datos["items"]] == [False, False, True]
    assert all(isinstance(f["amount_cop"], int) for f in datos["items"])
    assert {f["member_first_name"] for f in datos["items"]} == {"Lucía"}


@pytest.mark.parametrize(
    ("voided", "claves"),
    [("false", ["vigente", "retro"]), ("true", ["anulado"])],
)
async def test_filtra_por_voided(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    voided: str,
    claves: list[str],
) -> None:
    ids = await _pagos(session)
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(ids["lucia"]), params={"voided": voided}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids[k]) for k in claves]
    assert r.json()["total"] == len(claves)


async def test_q_es_la_referencia_exacta(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _pagos(session)
    coach = await usuario_real("coach")
    r = await app_http.get(ruta(ids["lucia"]), params={"q": "neq-55"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids["retro"])]
    r = await app_http.get(ruta(ids["lucia"]), params={"q": "gomez"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


async def test_pagina_con_limit_y_offset(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _pagos(session)
    admin = await usuario_real("admin")
    r = await app_http.get(
        ruta(ids["lucia"]), params={"limit": 1, "offset": 2}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert (datos["total"], datos["limit"], datos["offset"]) == (3, 1, 2)
    assert [f["id"] for f in datos["items"]] == [str(ids["anulado"])]


async def test_un_socio_dado_de_baja_devuelve_sus_pagos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _pagos(session)
    admin = await usuario_real("admin")
    r = await app_http.get(ruta(ids["ana"]), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids["de_ana"])]


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
        ({"voided": "quizas"}, "voided"),
        ({"q": "a" * 101}, "q"),
    ],
    ids=["limit-0", "limit-201", "offset-negativo", "voided-no-booleano", "q-101"],
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
    assert "quizas" not in error["message"]


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


async def test_q_no_gasta_la_cubeta_de_busquedas_de_personas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _pagos(session)
    coach = await usuario_real("coach")
    destino = ruta(ids["lucia"])
    for numero in range(LIMITE_DE_BUSQUEDAS + 1):
        r = await app_http.get(destino, params={"q": "NEQ-55"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text


async def test_el_openapi_de_la_ruta_declara_sus_errores_sin_429(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][RUTA_OPENAPI]["get"]
    assert set(operacion["responses"]) == {"200", "401", "403", "404", "422", "500", "503"}
    assert operacion["tags"] == ["payments"]
    nombres = {p["name"] for p in operacion["parameters"] if p["in"] == "query"}
    assert nombres == {"limit", "offset", "q", "voided"}
    respuesta = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert respuesta == {"$ref": "#/components/schemas/Page_PaymentRow_"}
