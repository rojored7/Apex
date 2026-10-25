"""`GET /api/v1/memberships` y `GET /api/v1/memberships/{membership_id}` por HTTP (S3-B7, US-091;
D18, D27, L-9, M-2, M-4, S3-D45, E2).

- admin y coach: 200 `{items, total, limit, offset}` (25 por defecto) con filas `MembershipRow`
  (claves exactas) y `Cache-Control: no-store`; `member` 403 `forbidden`; sin token 401;
- 422 `validation_error` con `field`: `limit` 0 y 201, `offset` -1, `status=vigente` y un
  `status` de 101 caracteres (`status`), fechas invertidas (`ends_to`), `ends_from` de 2019
  (`ends_from`), `plan_id` y `member_id` que no son UUID;
- detalle: 200 `MembershipOut` (claves exactas, con congelaciones y `paid_cop`); 404
  `membership_not_found`; 422 con `field="membership_id"` si no es UUID; 403 `member`; 401;
- límite con `q` (L-1, M-2, S3-D45): la cubeta `PII_SEARCH_BUCKET` (`members-search`, 60 por
  minuto por usuario) es la misma de `GET /members?q=`: la búsqueda 61 de aquí da 429 con
  `Retry-After`; 40 aquí y 20 en socios pasan y la 21 en socios (la 61 del usuario) da 429; otro
  usuario no se ve afectado; sin `q` no consume (61 seguidas dan 200 y la búsqueda siguiente
  también).

"Hoy" es 2026-10-21 (`reloj` de `api_prueba`), `expiring_days` 7.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.memberships._apoyo import (
    CAMPOS_FREEZE,
    CAMPOS_MEMBERSHIP,
    CAMPOS_ROW,
    MEMBERSHIPS,
    ruta_detalle,
)

LIMITE_DE_BUSQUEDAS = 60


async def _membresias(session: AsyncSession) -> dict[str, UUID]:
    """Una `active` por vencer (Lucía, del 2026-09-25 al 2026-10-25, con un pago de 50.000 y una
    congelación pasada del 1 al 2 de octubre), una `pending_payment` (Pedro) y una anulada."""
    plan = await make_plan(session)
    lucia = await make_member(session)
    pedro = await make_member(
        session,
        first_name="Pedro",
        last_name="Ruiz",
        document=unique_document(),
        phone=None,
        email=None,
    )
    gina = await make_member(
        session,
        first_name="Gina",
        last_name="Vélez",
        document=unique_document(),
        phone=None,
        email=None,
    )
    activa = await make_membership(
        session, lucia, plan, status="active", start=date(2026, 9, 25), end=date(2026, 10, 25)
    )
    await make_freeze(session, activa, date(2026, 10, 1), date(2026, 10, 2))
    await make_payment(session, activa, amount=50_000)
    pendiente = await make_membership(session, pedro, plan)
    anulada = await make_membership(session, gina, plan, status="cancelled")
    return {"activa": activa.id, "pendiente": pendiente.id, "anulada": anulada.id}


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_la_pagina_con_el_contrato(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    ids = await _membresias(session)
    quien = await usuario_real(rol)
    r = await app_http.get(MEMBERSHIPS, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["limit"], datos["offset"], datos["total"]) == (25, 0, 2)
    assert [f["id"] for f in datos["items"]] == [str(ids["activa"]), str(ids["pendiente"])]
    fila = datos["items"][0]
    assert set(fila) == CAMPOS_ROW
    assert (fila["status"], fila["paid_cop"], fila["agreed_price_cop"]) == (
        "expiring",
        50_000,
        120_000,
    )
    assert fila["member_name"] == "Lucía Gómez" and fila["plan_name"] == "Mensual"
    assert all(isinstance(fila[k], int) for k in ("paid_cop", "agreed_price_cop"))


async def test_filtra_por_status_separado_por_comas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _membresias(session)
    coach = await usuario_real("coach")
    r = await app_http.get(
        MEMBERSHIPS, params={"status": "pending_payment,cancelled"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    assert {f["id"] for f in r.json()["items"]} == {str(ids["pendiente"]), str(ids["anulada"])}


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    for ruta in (MEMBERSHIPS, ruta_detalle(uuid4())):
        r = await app_http.get(ruta, headers=cabeceras(socio))
        assert r.status_code == 403, (ruta, r.text)
        assert r.json()["error"]["code"] == "forbidden"
        sin_token = await app_http.get(ruta)
        assert sin_token.status_code == 401, ruta
        assert sin_token.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 201}, "limit"),
        ({"offset": -1}, "offset"),
        ({"status": "vigente"}, "status"),
        ({"status": "active,vigente"}, "status"),
        ({"status": "a" * 101}, "status"),
        ({"ends_from": "2026-11-01", "ends_to": "2026-10-31"}, "ends_to"),
        ({"ends_from": "2019-12-31"}, "ends_from"),
        ({"ends_to": "9999-12-31"}, "ends_to"),
        ({"ends_from": "no-es-fecha"}, "ends_from"),
        ({"plan_id": "no-es-uuid"}, "plan_id"),
        ({"member_id": "no-es-uuid"}, "member_id"),
    ],
    ids=[
        "limit-0",
        "limit-201",
        "offset-negativo",
        "status-desconocido",
        "status-uno-de-dos",
        "status-101",
        "fechas-invertidas",
        "desde-2019",
        "hasta-9999",
        "fecha-mal-formada",
        "plan-no-uuid",
        "socio-no-uuid",
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
    r = await app_http.get(MEMBERSHIPS, params=params, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert "vigente" not in error["message"]


async def test_limit_200_es_valido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(MEMBERSHIPS, params={"limit": 200}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200


# Detalle ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_el_detalle_da_la_membresia_con_sus_congelaciones(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    ids = await _membresias(session)
    quien = await usuario_real(rol)
    r = await app_http.get(ruta_detalle(ids["activa"]), headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == CAMPOS_MEMBERSHIP
    assert (datos["id"], datos["paid_cop"], datos["member_name"]) == (
        str(ids["activa"]),
        50_000,
        "Lucía Gómez",
    )
    assert [(c["frozen_from"], c["frozen_to"], c["days"]) for c in datos["freezes"]] == [
        ("2026-10-01", "2026-10-02", 2)
    ]
    assert set(datos["freezes"][0]) == CAMPOS_FREEZE


async def test_el_detalle_de_una_anulada_trae_el_motivo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    ids = await _membresias(session)
    admin = await usuario_real("admin")
    r = await app_http.get(ruta_detalle(ids["anulada"]), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancel_reason"] is not None


async def test_el_detalle_de_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_detalle(uuid4()), headers=cabeceras(coach))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "membership_not_found"


async def test_el_detalle_con_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ruta_detalle("no-es-uuid"), headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "membership_id"


# Límite de búsquedas (L-1, M-2, S3-D45) ----------------------------------------------------------


async def test_la_busqueda_61_en_un_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    for numero in range(LIMITE_DE_BUSQUEDAS):
        r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0
    r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(otro))
    assert r.status_code == 200, r.text


async def test_la_cubeta_de_busquedas_se_comparte_con_la_lista_de_socios(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """M-2: 40 búsquedas aquí y 20 en `GET /members?q=` pasan; la 61 del mismo usuario (la 21
    en socios) da 429, y después también aquí."""
    coach = await usuario_real("coach")
    for numero in range(40):
        r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    for numero in range(20):
        r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text


async def test_sin_q_no_consume_la_cubeta(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for numero in range(LIMITE_DE_BUSQUEDAS + 1):
        r = await app_http.get(MEMBERSHIPS, params={"status": "active"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERSHIPS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
