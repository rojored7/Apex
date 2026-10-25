"""`GET /api/v1/payments` por HTTP (S3-B8, US-098; D26, D27, M-2, M-4, M-8, L-2, S3-D45, S3-D47,
S3-D51, S3-D57, E2).

- admin y coach: 200 `{items, total, limit, offset}` (25 por defecto) con filas `PaymentRow`
  (claves exactas), montos enteros y `Cache-Control: no-store`; `member` 403 `forbidden`; sin
  token 401 `unauthorized`;
- 422 `validation_error` con `field`: `limit` 0 y 201, `offset` -1, `method=tarjeta`, `from`
  mal formada, sin zona o de 2019, `to` de hoy más 6 años, rango invertido (`to`), `voided` y
  `backdated` que no son booleanos, ids que no son UUID;
- `backdated=true` filtra los registrados más de 24 h después del pago (M-8);
- límite con `q` (M-2, S3-D45): la cubeta `PII_SEARCH_BUCKET` (60 por minuto por usuario) es la
  misma de `GET /members?q=`: la 61 de aquí da 429 con `Retry-After`; 30 en socios y 30 aquí
  pasan y la 61 aquí da 429; 40 aquí y 20 en socios pasan y la 21 en socios da 429; otro usuario
  no se ve afectado; sin `q` no consume.

"Hoy" es 2026-10-21 (`reloj` de `api_prueba`). Datos: dos pagos de la membresía de Lucía Gómez
registrados por un coach: 60.000 en efectivo el 2026-10-10T15:00Z (registrado 1 h después) y
40.000 por Nequi el 2026-10-05T15:00Z con referencia `NEQ-55`, registrado el 2026-10-08T15:00Z
(72 h después: `backdated`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.payments._apoyo import CAMPOS_ROW, PAYMENTS

LIMITE_DE_BUSQUEDAS = 60


async def _pagos(session: AsyncSession, quien: UsuarioPrueba) -> dict[str, UUID]:
    plan = await make_plan(session)
    socio = await make_member(session)
    membresia = await make_membership(session, socio, plan, status="active")
    vigente_pagado = datetime(2026, 10, 10, 15, tzinfo=UTC)
    retro_pagado = datetime(2026, 10, 5, 15, tzinfo=UTC)
    vigente = await make_payment(
        session,
        membresia,
        amount=60_000,
        paid_at=vigente_pagado,
        registered_by=quien.id,
        created_at=vigente_pagado + timedelta(hours=1),
    )
    retro = await make_payment(
        session,
        membresia,
        amount=40_000,
        method="nequi",
        reference="NEQ-55",
        paid_at=retro_pagado,
        registered_by=quien.id,
        created_at=retro_pagado + timedelta(hours=72),
    )
    return {"vigente": vigente.id, "retro": retro.id}


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_pagina_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    ids = await _pagos(session, quien)
    r = await app_http.get(PAYMENTS, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["limit"], datos["offset"], datos["total"]) == (25, 0, 2)
    assert [f["id"] for f in datos["items"]] == [str(ids["vigente"]), str(ids["retro"])]
    fila = datos["items"][0]
    assert set(fila) == CAMPOS_ROW
    assert type(fila["amount_cop"]) is int and fila["amount_cop"] == 60_000
    assert (fila["method"], fila["voided"], fila["backdated"]) == ("cash", False, False)
    assert (fila["member_first_name"], fila["member_last_name"], fila["plan_name"]) == (
        "Lucía",
        "Gómez",
        "Mensual",
    )
    assert fila["registered_by"] == str(quien.id)
    local, dominio = quien.email.split("@")
    assert fila["registered_by_name"] == f"{local[0]}•••@{dominio}"
    assert quien.email not in r.text


async def test_backdated_true_filtra_los_registrados_mas_de_24_h_despues(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    ids = await _pagos(session, coach)
    r = await app_http.get(PAYMENTS, params={"backdated": "true"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [str(ids["retro"])]
    assert r.json()["items"][0]["backdated"] is True
    r = await app_http.get(PAYMENTS, params={"backdated": "false"}, headers=cabeceras(coach))
    assert [f["id"] for f in r.json()["items"]] == [str(ids["vigente"])]


async def test_filtros_por_medio_rango_y_referencia(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    ids = await _pagos(session, coach)
    casos: list[tuple[dict[str, Any], list[UUID]]] = [
        ({"method": "nequi"}, [ids["retro"]]),
        ({"from": "2026-10-10T15:00:00Z", "to": "2026-11-01T05:00:00Z"}, [ids["vigente"]]),
        ({"from": "2026-10-01T05:00:00Z", "to": "2026-10-10T15:00:00Z"}, [ids["retro"]]),
        ({"from": "2026-10-10T10:00:00-05:00"}, [ids["vigente"]]),
        ({"q": "neq-55"}, [ids["retro"]]),
        ({"voided": "false", "method": "cash"}, [ids["vigente"]]),
    ]
    for params, esperados in casos:
        r = await app_http.get(PAYMENTS, params=params, headers=cabeceras(coach))
        assert r.status_code == 200, (params, r.text)
        assert [f["id"] for f in r.json()["items"]] == [str(i) for i in esperados], params


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(PAYMENTS, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(PAYMENTS)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"offset": -1}, "offset"),
        ({"method": "tarjeta"}, "method"),
        ({"from": "no-es-fecha"}, "from"),
        ({"from": "2026-10-01T05:00:00"}, "from"),
        ({"from": "2019-12-31T00:00:00Z"}, "from"),
        ({"to": "2032-10-21T00:00:00Z"}, "to"),
        ({"to": "9999-12-31T23:59:59Z"}, "to"),
        ({"from": "2026-10-20T00:00:00Z", "to": "2026-10-10T00:00:00Z"}, "to"),
        ({"voided": "quizas"}, "voided"),
        ({"backdated": "quizas"}, "backdated"),
        ({"member_id": "no-es-uuid"}, "member_id"),
        ({"membership_id": "no-es-uuid"}, "membership_id"),
        ({"registered_by": "no-es-uuid"}, "registered_by"),
        ({"q": "a" * 101}, "q"),
    ],
    ids=[
        "limit-0",
        "limit-201",
        "offset-negativo",
        "medio-desconocido",
        "from-mal-formada",
        "from-sin-zona",
        "from-2019",
        "to-hoy-mas-6-anios",
        "to-9999",
        "rango-invertido",
        "voided-no-booleano",
        "backdated-no-booleano",
        "socio-no-uuid",
        "membresia-no-uuid",
        "registro-no-uuid",
        "q-101",
    ],
)
async def test_parametros_invalidos_dan_422_con_el_campo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    params: dict[str, Any],
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(PAYMENTS, params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert "tarjeta" not in error["message"] and "2019" not in error["message"]


async def test_limit_200_es_valido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(PAYMENTS, params={"limit": 200}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200


# Límite de búsquedas (M-2, S3-D45) ---------------------------------------------------------------


async def test_la_busqueda_61_en_un_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    for numero in range(LIMITE_DE_BUSQUEDAS):
        r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0
    r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(otro))
    assert r.status_code == 200, r.text


async def test_30_en_socios_y_30_en_pagos_dan_429_en_la_61(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """M-2: la cubeta es una sola para las búsquedas de personas del mismo usuario."""
    coach = await usuario_real("coach")
    for numero in range(30):
        r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    for numero in range(30):
        r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text


async def test_la_cubeta_de_busquedas_se_comparte_con_la_lista_de_socios(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """M-2: 40 aquí y 20 en `GET /members?q=` pasan; la 21 en socios da 429 y después aquí."""
    coach = await usuario_real("coach")
    for numero in range(40):
        r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    for numero in range(20):
        r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text


async def test_sin_q_no_consume_la_cubeta(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for numero in range(LIMITE_DE_BUSQUEDAS + 1):
        r = await app_http.get(PAYMENTS, params={"voided": "false"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(PAYMENTS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
