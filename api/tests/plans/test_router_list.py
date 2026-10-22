"""`GET /api/v1/plans` y `GET /api/v1/plans/{plan_id}` por HTTP (S2-B9; US-079; S2-D26).

- admin: 200 `{items, total, limit, offset}` (25 por defecto) con activos e inactivos vivos;
  `?active=false` solo inactivos; `q` busca sin mayúsculas ni tildes; nunca un dado de baja;
- coach: `?active=true` 200 con solo activos; `?active=false` o sin parámetro: 403 `forbidden`;
- `member` 403 en las dos rutas; sin token 401 `unauthorized`;
- `GET /plans/{id}`: un plan inactivo da 403 al coach y 200 al admin; un dado de baja o
  inexistente, 404 `plan_not_found` para los dos; un id que no es UUID, 422 `field=plan_id`;
- 422 con `field`: `limit` 500, 201 y 0, `offset` -1, `active=talvez` y `q` de 101;
- un `q` con caracteres de control (`%00`, `%1f`) da 422 `field=q` (contrato común
  `SearchQuery`, deuda de S2-B8), nunca 500.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.plans import make_plan
from tests.plans._apoyo import CAMPOS_PLAN, PLANS


async def _planes(session: AsyncSession) -> dict[str, str]:
    """Un activo, un inactivo y uno dado de baja; devuelve sus ids como texto."""
    activo = await make_plan(session, name="Mensual")
    inactivo = await make_plan(session, name="Anual", duration_days=365, is_active=False)
    baja = await make_plan(session, name="Semestral", deleted_at=T0 - timedelta(days=1))
    return {"activo": str(activo.id), "inactivo": str(inactivo.id), "baja": str(baja.id)}


def _ids(respuesta: Any) -> list[str]:
    return [fila["id"] for fila in respuesta.json()["items"]]


# Lista ------------------------------------------------------------------------------------


async def test_el_admin_recibe_la_pagina_con_activos_e_inactivos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    planes = await _planes(session)
    admin = await usuario_real("admin")
    r = await app_http.get(PLANS, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == {"items", "total", "limit", "offset"}
    assert (datos["limit"], datos["offset"], datos["total"]) == (25, 0, 2)
    assert _ids(r) == [planes["inactivo"], planes["activo"]]  # "Anual" antes que "Mensual"
    for fila in datos["items"]:
        assert set(fila) == CAMPOS_PLAN
        assert type(fila["price_cop"]) is int


async def test_el_admin_con_active_false_ve_solo_los_inactivos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    planes = await _planes(session)
    admin = await usuario_real("admin")
    r = await app_http.get(PLANS, params={"active": "false"}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert _ids(r) == [planes["inactivo"]]


async def test_el_coach_con_active_true_ve_solo_los_activos(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    planes = await _planes(session)
    coach = await usuario_real("coach")
    r = await app_http.get(PLANS, params={"active": "true"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert _ids(r) == [planes["activo"]]
    assert all(fila["is_active"] is True for fila in r.json()["items"])


@pytest.mark.parametrize(
    "params", [{}, {"active": "false"}, {"q": "mensual"}], ids=["sin", "inactivos", "solo-q"]
)
async def test_el_coach_sin_active_true_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    params: dict[str, str],
) -> None:
    await _planes(session)
    coach = await usuario_real("coach")
    r = await app_http.get(PLANS, params=params, headers=cabeceras(coach))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert "items" not in r.text


async def test_la_busqueda_por_http_ignora_mayusculas_y_tildes(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    promo = await make_plan(session, name="Promoción")
    await make_plan(session, name="Trimestral")
    admin = await usuario_real("admin")
    for termino in ("PROMOCION", "promoción", "promo"):
        r = await app_http.get(PLANS, params={"q": termino}, headers=cabeceras(admin))
        assert r.status_code == 200, (termino, r.text)
        assert _ids(r) == [str(promo.id)], termino


@pytest.mark.parametrize("ruta", ["lista", "detalle"])
async def test_member_recibe_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    ruta: str,
) -> None:
    planes = await _planes(session)
    socio = await usuario_real("member")
    url = PLANS if ruta == "lista" else f"{PLANS}/{planes['activo']}"
    r = await app_http.get(url, params={"active": "true"}, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("ruta", ["lista", "detalle"])
async def test_sin_token_da_401(app_http: AsyncClient, ruta: str) -> None:
    url = PLANS if ruta == "lista" else f"{PLANS}/{uuid4()}"
    r = await app_http.get(url)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("query", "campo"),
    [
        ("limit=500", "limit"),
        ("limit=201", "limit"),
        ("limit=0", "limit"),
        ("offset=-1", "offset"),
        ("active=talvez", "active"),
        ("q=" + "x" * 101, "q"),
    ],
    ids=["limit-500", "limit-201", "limit-0", "offset-negativo", "active", "q-largo"],
)
async def test_parametros_invalidos_dan_422_con_el_campo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    query: str,
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(f"{PLANS}?{query}", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo


@pytest.mark.parametrize("termino", ["a\x00b", "\x00", "a\x1fb"], ids=["nul", "solo-nul", "us"])
async def test_un_q_con_caracteres_de_control_da_422_y_nunca_500(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, termino: str
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(PLANS, params={"q": termino}, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "q"


async def test_limit_200_es_valido(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(PLANS, params={"limit": 200}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["limit"] == 200


# Detalle ----------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_un_plan_activo_lo_leen_admin_y_coach(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    planes = await _planes(session)
    quien = await usuario_real(rol)
    r = await app_http.get(f"{PLANS}/{planes['activo']}", headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert set(datos) == CAMPOS_PLAN
    assert datos["id"] == planes["activo"] and datos["name"] == "Mensual"
    assert datos["price_cop"] == 120_000 and type(datos["price_cop"]) is int


async def test_un_plan_inactivo_da_403_al_coach_y_200_al_admin(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    planes = await _planes(session)
    coach = await usuario_real("coach")
    admin = await usuario_real("admin")
    url = f"{PLANS}/{planes['inactivo']}"
    r = await app_http.get(url, headers=cabeceras(coach))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    r = await app_http.get(url, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


@pytest.mark.parametrize("rol", ["admin", "coach"])
@pytest.mark.parametrize("cual", ["baja", "inexistente"])
async def test_un_dado_de_baja_o_inexistente_da_404(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
    cual: str,
) -> None:
    planes = await _planes(session)
    quien = await usuario_real(rol)
    plan_id = planes["baja"] if cual == "baja" else str(uuid4())
    r = await app_http.get(f"{PLANS}/{plan_id}", headers=cabeceras(quien))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "plan_not_found"


async def test_un_id_que_no_es_uuid_da_422_con_field_plan_id(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(f"{PLANS}/no-es-uuid", headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "plan_id"
