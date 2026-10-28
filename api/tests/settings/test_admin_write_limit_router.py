"""Los cinco `PATCH /api/v1/settings/*` consumen `admin-write` (M-A de la revisión de seguridad
V10 del Sprint 3; S3-D100).

Una sola cubeta por usuario para las cinco rutas (y las demás escrituras de solo admin): tras
30 escrituras en el minuto, la 31 da 429 `rate_limited` con `Retry-After` en cualquiera de las
cinco y no guarda nada; otro admin pasa; las lecturas (`GET`) no consumen; el OpenAPI de las
cinco declara 429 y el de sus `GET` no.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario
from tests.settings._apoyo import API, CUERPOS, GYM_OK, fila

TOPE_POR_MINUTO = 30
PATCHES = (
    "/settings/gym",
    "/settings/privacy",
    "/settings/memberships",
    "/settings/payment_methods",
    "/settings/tv",  # genérica `/settings/{section}`: 404 `section_not_available`
)


async def test_las_cinco_comparten_admin_write_y_la_31_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    for i in range(TOPE_POR_MINUTO):
        ruta = PATCHES[i % len(PATCHES)]
        # Versión 0: 200 la primera vez en cada tipada, 409 después; 404 en la genérica.
        r = await app_http.patch(f"{API}{ruta}", json=CUERPOS[ruta], headers=cabeceras(admin))
        assert r.status_code in {200, 404, 409}, r.text
    guardada = await fila(session, "gym")
    assert guardada is not None and guardada["version"] == 1
    for ruta in PATCHES:
        cuerpo = {**CUERPOS[ruta], "version": 1} if ruta != "/settings/tv" else CUERPOS[ruta]
        r = await app_http.patch(f"{API}{ruta}", json=cuerpo, headers=cabeceras(admin))
        assert r.status_code == 429, (ruta, r.text)
        assert r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
    session.expire_all()
    assert await fila(session, "gym") == guardada
    r = await app_http.patch(
        f"{API}/settings/gym", json={"value": GYM_OK, "version": 1}, headers=cabeceras(otro)
    )
    assert r.status_code == 200, r.text


async def test_las_lecturas_no_consumen_admin_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.get(f"{API}/settings/gym", headers=cabeceras(admin))
        assert r.status_code == 200, r.text
    r = await app_http.patch(
        f"{API}/settings/gym", json={"value": GYM_OK, "version": 0}, headers=cabeceras(admin)
    )
    assert r.status_code == 200, r.text


async def test_los_patch_comparten_admin_write_con_anular_un_pago(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    anular = f"{API}/payments/{uuid4()}/void"
    for _ in range(TOPE_POR_MINUTO):
        r = await app_http.post(
            anular, json={"reason": "Error de digitación"}, headers=cabeceras(admin)
        )
        assert r.status_code == 404, r.text
    r = await app_http.patch(
        f"{API}/settings/gym", json={"value": GYM_OK, "version": 0}, headers=cabeceras(admin)
    )
    assert r.status_code == 429, r.text


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/v1/settings/gym",
        "/api/v1/settings/privacy",
        "/api/v1/settings/memberships",
        "/api/v1/settings/payment_methods",
        "/api/v1/settings/{section}",
    ],
)
def test_el_openapi_de_los_cinco_patch_declara_el_429(api_prueba: FastAPI, ruta: str) -> None:
    esquema = api_prueba.openapi()["paths"][ruta]
    assert "429" in esquema["patch"]["responses"]
    assert "429" not in esquema["get"]["responses"]
