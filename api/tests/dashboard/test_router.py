"""`GET /api/v1/dashboard` (S4A-B8, US-108; S4A-D27, S4A-D29, S4A-D45).

- 200 para admin y coach con el mismo cuerpo salvo las finanzas (S4A-D29 ajustada por S4A-D118:
  `income_month_cop` `null` y frases de pagos sin monto para el coach); 403 `forbidden` para
  member; 401 sin token; claves exactas `CAMPOS_DASHBOARD` (los cinco futuros presentes y en
  `null`); `last_movements` con 10 como máximo; `Cache-Control: no-store`.
- `staff-read` (120 por minuto, S4A-D45): la 121.ª lectura del minuto da 429 `rate_limited` con
  `Retry-After`; otro usuario sigue pasando; la cubeta es la misma que la de `GET /audit`.
"""

from __future__ import annotations

from typing import Any, Final

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.ratelimit import USER_LIMITS
from tests.audit._apoyo import AUDIT, Actividad, sembrar_actividad
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.dashboard._apoyo import CAMPOS_DASHBOARD, CAMPOS_MOVEMENT, DASHBOARD, FUTUROS
from tests.factories.audit_chain import make_audit_chain

LIMITE_DE_LECTURAS: Final = USER_LIMITS["staff-read"][0]


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


async def _get(app_http: AsyncClient, cabeceras: Cabeceras, quien: UsuarioPrueba) -> Response:
    return await app_http.get(DASHBOARD, headers=cabeceras(quien))


def _sin_finanzas(cuerpo: dict[str, Any]) -> dict[str, Any]:
    """El cuerpo sin `income_month_cop` y con las frases tapadas (S4A-D118)."""
    resto = {k: v for k, v in cuerpo.items() if k not in ("income_month_cop", "last_movements")}
    return {**resto, "last_movements": [{**m, "phrase": None} for m in cuerpo["last_movements"]]}


async def test_admin_y_coach_reciben_200_con_el_mismo_cuerpo_salvo_las_finanzas(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    admin = await _get(app_http, cabeceras, ana)
    coach = await _get(app_http, cabeceras, juan)
    assert (admin.status_code, coach.status_code) == (200, 200), (admin.text, coach.text)
    cuerpo_admin, cuerpo_coach = admin.json(), coach.json()
    # S4A-D118: el coach no recibe ingresos ni montos; todo lo demás es idéntico.
    assert isinstance(cuerpo_admin["income_month_cop"], int)
    assert cuerpo_coach["income_month_cop"] is None
    assert all("$" not in m["phrase"] for m in cuerpo_coach["last_movements"])
    assert any("$ 120.000" in m["phrase"] for m in cuerpo_admin["last_movements"])
    assert _sin_finanzas(cuerpo_admin) == _sin_finanzas(cuerpo_coach)
    frases_admin = [m["phrase"] for m in cuerpo_admin["last_movements"]]
    frases_coach = [m["phrase"] for m in cuerpo_coach["last_movements"]]
    assert [f.replace("$ 120.000 de ", "") for f in frases_admin] == frases_coach


async def test_el_cuerpo_tiene_las_claves_del_contrato_y_los_futuros_en_null(
    app_http: AsyncClient, actividad: Actividad, juan: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _get(app_http, cabeceras, juan)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_DASHBOARD
    assert {campo: cuerpo[campo] for campo in FUTUROS} == dict.fromkeys(FUTUROS)
    assert cuerpo["today"] == "2026-10-21"
    assert cuerpo["income_month"] == "2026-10"
    assert cuerpo["income_month_cop"] is None  # juan es coach (S4A-D118)
    assert cuerpo["last_movements"], "la actividad deja frases"
    assert all(set(m) == CAMPOS_MOVEMENT for m in cuerpo["last_movements"])
    assert r.headers["cache-control"] == "no-store"


async def test_last_movements_tiene_10_como_maximo(
    app_http: AsyncClient,
    session: AsyncSession,
    actividad: Actividad,
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    await make_audit_chain(session, 25, table_name="payments.payments", user_id=ana.id)
    r = await _get(app_http, cabeceras, ana)
    assert r.status_code == 200, r.text
    assert len(r.json()["last_movements"]) == 10


async def test_member_recibe_403(
    app_http: AsyncClient,
    actividad: Actividad,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    socio = await usuario_real("member")
    r = await _get(app_http, cabeceras, socio)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"


async def test_sin_token_da_401(app_http: AsyncClient, actividad: Actividad) -> None:
    r = await app_http.get(DASHBOARD)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_la_121_lectura_del_minuto_da_429_y_otro_usuario_pasa(
    app_http: AsyncClient,
    actividad: Actividad,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        r = await _get(app_http, cabeceras, juan)
        assert r.status_code == 200, (numero, r.text)
    r = await _get(app_http, cabeceras, juan)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    r = await _get(app_http, cabeceras, ana)
    assert r.status_code == 200, r.text


async def test_la_cubeta_es_la_misma_que_la_de_audit(
    app_http: AsyncClient, actividad: Actividad, ana: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    """60 lecturas del tablero más 60 de `GET /audit` del mismo admin: la 121.ª (tablero) da 429."""
    mitad = LIMITE_DE_LECTURAS // 2
    for numero in range(mitad):
        r = await _get(app_http, cabeceras, ana)
        assert r.status_code == 200, (numero, r.text)
    for numero in range(mitad):
        r = await app_http.get(AUDIT, params={"limit": 1}, headers=cabeceras(ana))
        assert r.status_code == 200, (numero, r.text)
    r = await _get(app_http, cabeceras, ana)
    assert r.status_code == 429, r.text


def test_staff_read_es_de_120_por_minuto() -> None:
    assert USER_LIMITS["staff-read"] == (120, 60)


async def test_openapi_declara_dashboard_out_sin_parametros(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"][DASHBOARD]["get"]
    assert {"200", "401", "403", "429"} <= set(operacion["responses"])
    assert "422" not in operacion["responses"]
    assert not operacion.get("parameters")
    esquema = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert esquema.endswith("/DashboardOut")
