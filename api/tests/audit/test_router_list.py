"""`GET /api/v1/audit` (S4A-B4, US-102; S4A-D16, S4A-D45, S4A-D46).

Contrato:
- admin: 200 `Page[AuditRow]` (`items`, `total`, `limit`, `offset`; cada fila con `CAMPOS_ROW`
  exactos, sin `before` ni `after`) y `Cache-Control: no-store`; los filtros llegan por la query
  (`from` por alias); `offset=100000` da 200 vacío;
- coach y member 403; sin token 401;
- 422 `validation_error` con `field`: `action` desconocida, `limit` 201, `offset` 100.001, `from`
  extremo (`0001-01-01T00:00:00+05:00`) o sin zona, `to` en 9999, rango invertido o vacío
  (`field="to"`), `table` con mayúsculas, con tres segmentos o de 128 caracteres, `user_id` que
  no es UUID, `q` con un carácter de control; nunca 500;
- `staff-read` (120 por minuto, compartida con `GET /audit/{seq}`): la 121.ª lectura del minuto
  da 429 `rate_limited` con `Retry-After` y la 121.ª de otro admin pasa;
  `GET /audit/verify/last` nunca da 429 (ni con la cubeta agotada ni con 130 seguidas);
- OpenAPI: 422 y 429 declarados; `table` con patrón y `maxLength` 127; `limit` hasta 200.
El reloj está congelado (T0): todas las peticiones caen en la misma ventana.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from tests.audit._apoyo import AUDIT, CAMPOS_ROW, VERIFY_LAST, Actividad, sembrar_actividad
from tests.audit.conftest import CadenaDePrueba
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba

LIMITE_DE_LECTURAS = 120


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
    app_http: AsyncClient, cabeceras: Cabeceras, quien: UsuarioPrueba, **params: Any
) -> Any:
    return await app_http.get(AUDIT, params=params, headers=cabeceras(quien))


async def test_admin_recibe_la_pagina_con_la_forma_exacta(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, ana)

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (11, 25, 0)
    assert [f["seq"] for f in cuerpo["items"]] == list(range(11, 0, -1))
    assert all(set(f) == CAMPOS_ROW for f in cuerpo["items"])
    assert "apx1." not in r.text


async def test_los_filtros_llegan_por_la_query(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    casos: list[tuple[dict[str, Any], list[int]]] = [
        ({"table": "members.members"}, [6, 5, 4]),
        ({"action": "update", "table": "memberships.memberships"}, [11, 9]),
        ({"user_id": str(juan.id)}, [9, 8, 6, 5]),
        ({"record_id": str(actividad.payment_id), "table": "payments.payments"}, [10, 8]),
        ({"subject_member_id": str(actividad.member_id), "limit": 2, "offset": 1}, [10, 9]),
        ({"q": "PÉREZ", "action": "insert"}, [7, 4, 3]),
        ({"q": str(actividad.member_id), "table": "members.members"}, [6, 5, 4]),
        ({"from": "2026-10-21T15:00:00Z", "to": "2026-10-21T16:00:00Z", "limit": 3}, [11, 10, 9]),
        ({"to": "2026-10-21T10:00:00-05:00"}, []),
    ]
    for params, esperadas in casos:
        r = await _get(app_http, cabeceras, ana, **params)
        assert r.status_code == 200, (params, r.text)
        assert [f["seq"] for f in r.json()["items"]] == esperadas, params


async def test_la_fila_del_sistema_y_la_de_una_persona(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, ana, limit=200)
    filas = {f["seq"]: f for f in r.json()["items"]}
    assert (filas[1]["user_name"], filas[1]["user_email"]) == ("Sistema", "system@apex.local")
    assert (filas[3]["user_name"], filas[3]["user_email"]) == (
        "ana.perez",
        "ana.perez@ejemplo.local",
    )
    assert filas[3]["table_name"] == "plans.plans" and filas[3]["action"] == "insert"


async def test_offset_100000_da_200_vacio(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, ana, offset=100_000)
    assert r.status_code == 200, r.text
    assert (r.json()["items"], r.json()["total"], r.json()["offset"]) == ([], 11, 100_000)


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_member_reciben_403(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
) -> None:
    quien = await usuario_real(rol)
    r = await _get(app_http, cabeceras, quien)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


async def test_sin_token_401(app_http: AsyncClient) -> None:
    r = await app_http.get(AUDIT)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"action": "hack"}, "action"),
        ({"limit": 201}, "limit"),
        ({"limit": 0}, "limit"),
        ({"offset": 100_001}, "offset"),
        ({"offset": 1_000_001}, "offset"),
        ({"from": "0001-01-01T00:00:00+05:00"}, "from"),
        ({"from": "2026-10-01T00:00:00"}, "from"),
        ({"from": "2019-12-31T23:59:59Z"}, "from"),
        ({"to": "9999-12-31T00:00:00Z"}, "to"),
        ({"to": "2026-10-23T00:00:00Z"}, "to"),
        ({"from": "2026-10-21T00:00:00Z", "to": "2026-10-20T00:00:00Z"}, "to"),
        ({"from": "2026-10-21T00:00:00Z", "to": "2026-10-21T00:00:00Z"}, "to"),
        ({"table": "Members.members"}, "table"),
        ({"table": "members.members.extra"}, "table"),
        ({"table": "a" * 64 + "." + "b" * 63}, "table"),
        ({"user_id": "no-es-uuid"}, "user_id"),
        ({"record_id": "123"}, "record_id"),
        ({"record_id": "6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b"}, "record_id"),
        ({"table": "members.socios"}, "table"),
        ({"subject_member_id": "x"}, "subject_member_id"),
        ({"q": "ana\x00"}, "q"),
        ({"q": "a" * 101}, "q"),
    ],
    ids=[
        "action",
        "limit-201",
        "limit-0",
        "offset-100001",
        "offset-millon",
        "from-anio-1",
        "from-sin-zona",
        "from-bajo-piso",
        "to-9999",
        "to-sobre-techo",
        "invertido",
        "vacio",
        "table-mayus",
        "table-tres",
        "table-128",
        "user-id",
        "record-id",
        "record-id-sin-table",
        "table-no-auditable",
        "subject",
        "q-nul",
        "q-larga",
    ],
)
async def test_422_con_el_campo_y_nunca_500(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
    reloj: FrozenClock,
    params: dict[str, Any],
    campo: str,
) -> None:
    r = await _get(app_http, cabeceras, ana, **params)
    assert r.status_code == 422, (params, r.status_code, r.text)
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    for valor in params.values():
        if isinstance(valor, str) and len(valor) > 3:
            assert valor not in error["message"]


async def test_la_121_del_minuto_da_429_y_otro_admin_pasa(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    for numero in range(LIMITE_DE_LECTURAS):
        r = await _get(app_http, cabeceras, admin)
        assert r.status_code == 200, (numero, r.text)
    caplog.set_level(logging.WARNING)
    r = await _get(app_http, cabeceras, admin)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    cubetas = [getattr(rec, "bucket", None) for rec in caplog.records]
    assert "staff-read" in cubetas, cubetas
    r = await _get(app_http, cabeceras, otro)
    assert r.status_code == 200, r.text


async def test_lista_y_detalle_comparten_la_cubeta(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    for numero in range(LIMITE_DE_LECTURAS // 2):
        r = await _get(app_http, cabeceras, ana)
        assert r.status_code == 200, (numero, r.text)
        r = await app_http.get(f"{AUDIT}/1", headers=cabeceras(ana))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(f"{AUDIT}/1", headers=cabeceras(ana))
    assert r.status_code == 429, r.text
    r = await _get(app_http, cabeceras, ana)
    assert r.status_code == 429, r.text


async def test_verify_last_nunca_da_429(
    app_http: AsyncClient,
    audit_chain_factory: CadenaDePrueba,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        r = await _get(app_http, cabeceras, ana)
        assert r.status_code == 200, (numero, r.text)
    assert (await _get(app_http, cabeceras, ana)).status_code == 429
    for numero in range(130):
        r = await app_http.get(VERIFY_LAST, headers=cabeceras(ana))
        assert r.status_code == 200, (numero, r.text)


def test_openapi_declara_422_429_y_los_parametros(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/audit"]["get"]
    assert {"401", "403", "422", "429"} <= set(operacion["responses"])
    assert "404" not in operacion["responses"]
    parametros = {p["name"]: p for p in operacion["parameters"]}
    assert set(parametros) == {
        "limit",
        "offset",
        "q",
        "from",
        "to",
        "user_id",
        "table",
        "record_id",
        "subject_member_id",
        "action",
    }
    tabla = parametros["table"]["schema"]
    tabla = next((s for s in tabla.get("anyOf", []) if s.get("type") == "string"), tabla)
    assert tabla["maxLength"] == 127
    assert tabla["pattern"] == r"^[a-z_]{1,63}\.[a-z_]{1,63}$"
    assert parametros["limit"]["schema"]["maximum"] == 200
