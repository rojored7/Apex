"""`GET /api/v1/memberships/summary` por HTTP (S3-B7, US-092 criterios 1 y 9; D27, S3-D53).

- admin y coach: 200 con exactamente cinco enteros (`active`, `expiring`, `expired`, `frozen`,
  `pending_payment`) y `Cache-Control: no-store`; `member` 403 `forbidden`; sin token 401;
- la ruta se declara antes de `/memberships/{membership_id}`: "summary" nunca se lee como un id
  (sería 422 por UUID); la comprobación estructural recorre las rutas efectivas de la app;
- OpenAPI: sin parámetros, sin 422 ni 429; respuesta `MembershipSummaryOut`.

Datos (hoy 2026-10-21, `expiring_days` 7): una `active` del 1 al 31 de octubre (faltan 10 días),
una `pending_payment` de hoy y una anulada: `active` 1, `pending_payment` 1, el resto 0.
"""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import effective_routes
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import CAMPOS_RESUMEN, RESUMEN

RUTA_RESUMEN = "/api/v1/memberships/summary"
RUTA_DETALLE = "/api/v1/memberships/{membership_id}"


async def _datos(session: AsyncSession) -> None:
    plan = await make_plan(session)
    for nombre, cambios in (
        ("Vigente", {"status": "active", "start": date(2026, 10, 1), "end": date(2026, 10, 31)}),
        ("Pendiente", {}),
        ("Anulada", {"status": "cancelled"}),
    ):
        socio = await make_member(
            session,
            first_name=nombre,
            last_name="Resumen",
            document=unique_document(),
            phone=None,
            email=None,
        )
        await make_membership(session, socio, plan, **cambios)


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_cinco_enteros(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    await _datos(session)
    quien = await usuario_real(rol)
    r = await app_http.get(RESUMEN, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == CAMPOS_RESUMEN
    assert all(type(valor) is int for valor in datos.values())
    assert datos == {"active": 1, "expiring": 0, "expired": 0, "frozen": 0, "pending_payment": 1}


async def test_sin_socios_el_resumen_es_cero(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(RESUMEN, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json() == dict.fromkeys(CAMPOS_RESUMEN, 0)


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(RESUMEN, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(RESUMEN)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


def test_summary_se_declara_antes_que_el_detalle(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    rutas = [
        (ruta.path, metodo)
        for ruta in effective_routes(app)[0]
        for metodo in sorted(ruta.methods or ())
    ]
    assert rutas.index((RUTA_RESUMEN, "GET")) < rutas.index((RUTA_DETALLE, "GET"))


def test_el_openapi_del_resumen_no_tiene_parametros_ni_422_ni_429(
    settings_prueba: Settings,
) -> None:
    operacion = create_app(settings_prueba, run_migrations_on_startup=False).openapi()["paths"][
        RUTA_RESUMEN
    ]["get"]
    assert "parameters" not in operacion
    assert {"200", "401", "403"} <= set(operacion["responses"])
    assert not {"422", "429", "404"} & set(operacion["responses"])
    ref = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/MembershipSummaryOut")
