"""`POST /api/v1/plans` consume `admin-write` (M-A de la revisión de seguridad V10 del Sprint 3;
S3-D100).

La cubeta es la de las demás escrituras de solo admin (anular pago, anular membresía, baja y
reactivación de socios, settings y usuarios): 30 por minuto por usuario. La 31 del minuto da
429 `rate_limited` con `Retry-After` y no crea nada; otro admin pasa; el 403 del coach no
consume cupo (el rol se comprueba antes); el OpenAPI declara 429.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.plans._apoyo import PLANS, cuantos_planes, cuerpo

TOPE_POR_MINUTO = 30


async def test_la_31_del_minuto_da_429_y_no_crea_el_plan(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    for i in range(TOPE_POR_MINUTO):
        r = await app_http.post(PLANS, json=cuerpo(name=f"Plan {i}"), headers=cabeceras(admin))
        assert r.status_code == 201, r.text
    antes = await cuantos_planes(session)
    r = await app_http.post(PLANS, json=cuerpo(name="Plan 31"), headers=cabeceras(admin))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert await cuantos_planes(session) == antes
    r = await app_http.post(PLANS, json=cuerpo(name="Plan del otro"), headers=cabeceras(otro))
    assert r.status_code == 201, r.text


async def test_crear_planes_comparte_admin_write_con_anular_una_membresia(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    cancelar = f"/api/v1/memberships/{uuid4()}/cancel"
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(
            cancelar, json={"reason": "Error de digitación"}, headers=cabeceras(admin)
        )
        assert r.status_code == 404, r.text
    r = await app_http.post(PLANS, json=cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 429, r.text


async def test_el_403_del_coach_no_consume_cupo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.post(PLANS, json=cuerpo(), headers=cabeceras(coach))
        assert r.status_code == 403, r.text


def test_el_openapi_de_crear_plan_declara_el_429(api_prueba: FastAPI) -> None:
    operacion = api_prueba.openapi()["paths"]["/api/v1/plans"]["post"]
    assert set(operacion["responses"]) == {"201", "401", "403", "409", "422", "429", "500", "503"}
