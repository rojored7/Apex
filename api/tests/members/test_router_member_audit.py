"""`GET /api/v1/members/{member_id}/audit` (S4A-B5, US-106; S4A-D20, S4A-D45, S4A-D54).

Contrato:
- admin y coach: 200 `Page[MemberHistoryItem]` con el MISMO cuerpo (mismos campos, sin
  `user_email`, sin valores) y `Cache-Control: no-store`; también sobre un socio dado de baja;
- 404 `member_not_found` si el socio no existe; 403 para `member`; 401 sin token;
- 422 `validation_error` con `field`: `limit` 0 o 201, `offset` 100.001 (`MAX_AUDIT_OFFSET`,
  S4A-D45), `member_id` que no es UUID, `q` con un carácter de control; nunca 500;
- `staff-read` (120 por minuto, compartida con `GET /audit` y `GET /audit/{seq}`): la 121.ª
  lectura del minuto da 429 `rate_limited` con `Retry-After`; 60 aquí más 61 en `/audit` del
  mismo admin dan 429 y otro usuario pasa;
- OpenAPI: 404, 422 y 429 declarados; `limit`, `offset` y `q`.
Datos: `sembrar_actividad` sobre la cadena vaciada (reloj congelado en T0); las ocho entradas de
la socia Lucía son las 11 a la 4 (tabla a mano en `tests/audit/test_member_history.py`).
"""

from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service as members_service
from tests.audit._apoyo import (
    ANA_EMAIL,
    ANA_NOMBRE,
    AUDIT,
    IP_REVELAR,
    JUAN_EMAIL,
    JUAN_NOMBRE,
    MOTIVO_ANULACION,
    Actividad,
    sembrar_actividad,
)
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories import audit_chain

LIMITE_DE_LECTURAS: Final = 120
CAMPOS_ITEM: Final = frozenset(
    {"seq", "at", "user_id", "user_name", "action", "table_name", "record_id", "fields", "purpose"}
)
ESPERADO: Final = [
    (11, "update", "memberships.memberships", ANA_NOMBRE, ["status"]),
    (10, "update", "payments.payments", ANA_NOMBRE, ["voided", "voided_at", "voided_by"]),
    (9, "update", "memberships.memberships", JUAN_NOMBRE, ["status"]),
    (8, "insert", "payments.payments", JUAN_NOMBRE, []),
    (7, "insert", "memberships.memberships", ANA_NOMBRE, []),
    (6, "reveal", "members.members", JUAN_NOMBRE, ["phone"]),
    (5, "update", "members.members", JUAN_NOMBRE, ["email", "phone"]),
    (4, "insert", "members.members", ANA_NOMBRE, []),
]


def ruta(member_id: UUID | str) -> str:
    return f"/api/v1/members/{member_id}/audit"


@pytest.fixture
async def cadena_vacia(session: AsyncSession) -> None:
    """La cadena vacía dentro de la transacción de la prueba (como `audit_chain_factory`)."""
    await audit_chain.empty_audit(session)


@pytest.fixture
async def ana(cadena_vacia: None, usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin", email=ANA_EMAIL)


@pytest.fixture
async def juan(ana: UsuarioPrueba, usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach", email=JUAN_EMAIL)


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def _get(
    app_http: AsyncClient,
    cabeceras: Cabeceras,
    quien: UsuarioPrueba,
    member_id: UUID | str,
    **params: Any,
) -> Response:
    return await app_http.get(ruta(member_id), params=params, headers=cabeceras(quien))


# 200 -----------------------------------------------------------------------------------------


async def test_coach_y_admin_reciben_el_mismo_cuerpo(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    por_admin = await _get(app_http, cabeceras, ana, actividad.member_id)
    por_coach = await _get(app_http, cabeceras, juan, actividad.member_id)

    assert por_admin.status_code == 200, por_admin.text
    assert por_coach.status_code == 200, por_coach.text
    assert por_admin.json() == por_coach.json()
    assert por_admin.headers["cache-control"] == "no-store"
    assert por_coach.headers["cache-control"] == "no-store"
    cuerpo = por_coach.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (8, 25, 0)
    assert all(set(item) == CAMPOS_ITEM for item in cuerpo["items"])
    obtenido = [
        (i["seq"], i["action"], i["table_name"], i["user_name"], i["fields"])
        for i in cuerpo["items"]
    ]
    assert obtenido == ESPERADO
    assert all(i["purpose"] is None for i in cuerpo["items"])


async def test_el_cuerpo_no_lleva_correos_blobs_ni_valores(
    app_http: AsyncClient, actividad: Actividad, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, juan, actividad.member_id, limit=200)
    assert r.status_code == 200, r.text
    for prohibido in (
        "@",
        "apx1.",
        "user_email",
        "reference",
        "void_reason",
        MOTIVO_ANULACION,
        IP_REVELAR,
        "_idx",
    ):
        assert prohibido not in r.text, prohibido


async def test_q_y_paginacion_llegan_por_la_query(
    app_http: AsyncClient, actividad: Actividad, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    casos: list[tuple[dict[str, Any], list[int], int]] = [
        ({"q": "juan"}, [9, 8, 6, 5], 4),
        ({"q": "ejemplo.local"}, [], 0),
        ({"limit": 3, "offset": 2}, [9, 8, 7], 8),
        ({"offset": 100_000}, [], 8),
    ]
    for params, esperadas, total in casos:
        r = await _get(app_http, cabeceras, juan, actividad.member_id, **params)
        assert r.status_code == 200, (params, r.text)
        assert [i["seq"] for i in r.json()["items"]] == esperadas, params
        assert r.json()["total"] == total, params


async def test_un_socio_dado_de_baja_devuelve_su_historial(
    app_http: AsyncClient,
    session: AsyncSession,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    with actor_scope(ana.id):
        await members_service.deactivate(session, actividad.member_id)
        await session.commit()

    r = await _get(app_http, cabeceras, juan, actividad.member_id)

    assert r.status_code == 200, r.text
    primera = r.json()["items"][0]
    assert (primera["seq"], primera["fields"]) == (12, ["deleted_at", "status"])


async def test_leer_el_historial_no_agrega_entradas(
    app_http: AsyncClient,
    actividad: Actividad,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    primera = await _get(app_http, cabeceras, juan, actividad.member_id)
    segunda = await _get(app_http, cabeceras, juan, actividad.member_id)
    assert primera.status_code == segunda.status_code == 200, primera.text
    assert primera.json() == segunda.json()


# Errores -------------------------------------------------------------------------------------


async def test_socio_inexistente_404(
    app_http: AsyncClient, cadena_vacia: None, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, juan, uuid4())
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_socio_inexistente_con_offset_fuera_de_rango_da_404(
    app_http: AsyncClient, cadena_vacia: None, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    """Duda 4 de B5: el socio se comprueba antes que el rango del `offset`."""
    r = await _get(app_http, cabeceras, juan, uuid4(), offset=100_001)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_member_recibe_403(
    app_http: AsyncClient,
    actividad: Actividad,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    socio_usuario = await usuario_real("member", member_id=actividad.member_id)
    r = await _get(app_http, cabeceras, socio_usuario, actividad.member_id)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


async def test_sin_token_401(app_http: AsyncClient) -> None:
    r = await app_http.get(ruta(uuid4()))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"offset": 100_001}, "offset"),
        ({"offset": -1}, "offset"),
        ({"q": "juan\x00"}, "q"),
    ],
    ids=["limit-0", "limit-201", "offset-100001", "offset-negativo", "q-nul"],
)
async def test_422_con_el_campo_y_nunca_500(
    app_http: AsyncClient,
    actividad: Actividad,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
    params: dict[str, Any],
    campo: str,
) -> None:
    r = await _get(app_http, cabeceras, juan, actividad.member_id, **params)
    assert r.status_code == 422, (params, r.status_code, r.text)
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)


async def test_member_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, cadena_vacia: None, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, juan, "no-es-uuid")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


# staff-read (S4A-D45) ------------------------------------------------------------------------


async def test_la_121_del_minuto_da_429_y_otro_usuario_pasa(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        r = await _get(app_http, cabeceras, juan, actividad.member_id, limit=1)
        assert r.status_code == 200, (numero, r.text)
    caplog.set_level(logging.WARNING)
    r = await _get(app_http, cabeceras, juan, actividad.member_id, limit=1)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    cubetas = [getattr(rec, "bucket", None) for rec in caplog.records]
    assert "staff-read" in cubetas, cubetas
    r = await _get(app_http, cabeceras, ana, actividad.member_id, limit=1)
    assert r.status_code == 200, r.text


async def test_la_cubeta_es_la_misma_que_la_de_audit(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    """60 lecturas del historial más 61 de `GET /audit` del mismo admin: la 121.ª da 429, y
    después también el historial."""
    mitad = LIMITE_DE_LECTURAS // 2
    for numero in range(mitad):
        r = await _get(app_http, cabeceras, ana, actividad.member_id, limit=1)
        assert r.status_code == 200, (numero, r.text)
    for numero in range(mitad):
        r = await app_http.get(AUDIT, params={"limit": 1}, headers=cabeceras(ana))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(AUDIT, params={"limit": 1}, headers=cabeceras(ana))
    assert r.status_code == 429, r.text
    r = await _get(app_http, cabeceras, ana, actividad.member_id, limit=1)
    assert r.status_code == 429, r.text


# OpenAPI -------------------------------------------------------------------------------------


async def test_openapi_declara_404_422_y_429(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/members/{member_id}/audit"]["get"]
    assert {"200", "401", "403", "404", "422", "429"} <= set(operacion["responses"])
    parametros = {p["name"]: p for p in operacion["parameters"]}
    assert {"member_id", "limit", "offset", "q"} <= set(parametros)
    assert parametros["limit"]["schema"]["maximum"] == 200
    referencia = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert referencia.endswith("Page_MemberHistoryItem_")
