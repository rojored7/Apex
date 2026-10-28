"""Escrituras de usuarios con `admin-write` y las tres de emergencia exentas (M-A de la revisión
de seguridad V10 del Sprint 3; S3-D100).

`POST /users`, `POST /users/{user_id}/resend-link`, `PATCH /users/{user_id}` y
`DELETE /users/{user_id}` consumen la cubeta `admin-write` (30 por minuto por usuario, la de
las demás escrituras de solo admin): la 31 da 429 `rate_limited` con `Retry-After` y no crea la
cuenta; otro admin pasa. `lock`, `unlock` y `revoke-sessions` son la respuesta a un incidente y
no tienen tope: con la cubeta agotada siguen respondiendo (aquí 404 sobre un id inexistente).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario

API = "/api/v1"
TOPE_POR_MINUTO = 30


async def _cuentas(session: AsyncSession) -> int:
    return int(await session.scalar(text("SELECT count(*) FROM auth.users")) or 0)


async def _escritura(cliente: AsyncClient, paso: int, h: dict[str, str]) -> Response:
    """Una de las cuatro escrituras con tope, según `paso % 4`."""
    if paso % 4 == 0:
        correo = f"v10-{uuid4().hex[:8]}@apex.test"
        return await cliente.post(
            f"{API}/users", json={"email": correo, "role": "coach"}, headers=h
        )
    if paso % 4 == 1:
        return await cliente.post(f"{API}/users/{uuid4()}/resend-link", headers=h)
    if paso % 4 == 2:
        return await cliente.patch(f"{API}/users/{uuid4()}", json={"role": "coach"}, headers=h)
    return await cliente.delete(f"{API}/users/{uuid4()}", headers=h)


async def test_las_cuatro_comparten_admin_write_y_la_31_da_429(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    otro = await usuario_real("admin")
    h = cabeceras(admin)
    for paso in range(TOPE_POR_MINUTO):
        r = await _escritura(app_http, paso, h)
        assert r.status_code == (201 if paso % 4 == 0 else 404), r.text
    antes = await _cuentas(session)
    for paso in range(4):
        r = await _escritura(app_http, paso, h)
        assert r.status_code == 429, r.text
        assert r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
    assert await _cuentas(session) == antes
    r = await _escritura(app_http, 0, cabeceras(otro))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("accion", ["lock", "unlock", "revoke-sessions"])
async def test_las_de_emergencia_no_tienen_tope_con_la_cubeta_agotada(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, accion: str
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    for _ in range(TOPE_POR_MINUTO):
        assert (await _escritura(app_http, 3, h)).status_code == 404
    assert (await _escritura(app_http, 3, h)).status_code == 429
    for _ in range(TOPE_POR_MINUTO + 1):
        r = await app_http.post(f"{API}/users/{uuid4()}/{accion}", headers=h)
        assert r.status_code == 404, r.text


@pytest.mark.parametrize(
    ("metodo", "ruta", "con_429"),
    [
        ("post", "/api/v1/users", True),
        ("post", "/api/v1/users/{user_id}/resend-link", True),
        ("patch", "/api/v1/users/{user_id}", True),
        ("delete", "/api/v1/users/{user_id}", True),
        ("post", "/api/v1/users/{user_id}/lock", False),
        ("post", "/api/v1/users/{user_id}/unlock", False),
        ("post", "/api/v1/users/{user_id}/revoke-sessions", False),
    ],
)
def test_el_openapi_declara_el_429_solo_en_las_cuatro(
    api_prueba: FastAPI, metodo: str, ruta: str, con_429: bool
) -> None:
    respuestas = api_prueba.openapi()["paths"][ruta][metodo]["responses"]
    assert ("429" in respuestas) is con_429
