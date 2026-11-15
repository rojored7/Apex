"""Rutas `/settings/tv` con el api real (S8-C1, US-175; S8-D30, S8-D32, L-7)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.security import hash_opaque_token
from tests.conftest import Cabeceras, CrearUsuario
from tests.settings._apoyo import API

TV = f"{API}/settings/tv"
EDICION = {"refresh_seconds": 45, "show_leaderboard": False}
RUTAS = (
    ("GET", TV),
    ("PATCH", TV),
    ("POST", f"{TV}/regenerate-token"),
    ("POST", f"{TV}/revoke-token"),
)


@pytest.mark.parametrize("rol", ["coach", "member"])
@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
async def test_coach_y_socio_403(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
    metodo: str,
    ruta: str,
) -> None:
    usuario = await usuario_real(rol)
    cuerpo = {"value": EDICION, "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(metodo, ruta, headers=cabeceras(usuario), json=cuerpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_sin_token_401(app_http: AsyncClient) -> None:
    for metodo, ruta in RUTAS:
        r = await app_http.request(metodo, ruta)
        assert r.status_code == 401, (metodo, ruta)


async def test_409_de_version(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    r = await app_http.post(f"{TV}/regenerate-token", headers=h)
    assert r.status_code == 200 and r.json()["version"] == 1
    viejo = await app_http.patch(TV, headers=h, json={"value": EDICION, "version": 0})
    assert viejo.status_code == 409 and viejo.json()["error"]["code"] == "version_conflict"
    bien = await app_http.patch(TV, headers=h, json={"value": EDICION, "version": 1})
    assert bien.status_code == 200 and bien.json()["version"] == 2
    assert bien.json()["value"]["has_token"] is True


async def test_no_store_en_regenerate(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(f"{TV}/regenerate-token", headers=cabeceras(admin))
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"token", "url", "token_last4", "rotated_at", "version"}
    assert cuerpo["url"].endswith(f"/tv#token={cuerpo['token']}")
    assert cuerpo["token_last4"] == cuerpo["token"][-4:]
    leida = await app_http.get(TV, headers=cabeceras(admin))
    assert leida.headers["cache-control"] == "no-store"
    assert cuerpo["token"] not in leida.text
    assert hash_opaque_token(cuerpo["token"]) not in leida.text
    assert leida.json()["value"]["has_token"] is True


async def test_revoke_por_http(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    await app_http.post(f"{TV}/regenerate-token", headers=h)
    r = await app_http.post(f"{TV}/revoke-token", headers=h)
    assert r.status_code == 200 and r.json()["value"]["has_token"] is False
    assert r.headers["cache-control"] == "no-store"


async def test_cubeta_admin_write(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """Las dos acciones y el `PATCH` comparten `admin-write`: la 31 da 429."""
    admin = await usuario_real("admin")
    h = cabeceras(admin)
    for i in range(30):
        ruta = f"{TV}/revoke-token" if i % 2 else f"{TV}/regenerate-token"
        r = await app_http.post(ruta, headers=h)
        assert r.status_code == 200, r.text
    for metodo, ruta in RUTAS[1:]:
        cuerpo = {"value": EDICION, "version": 0} if metodo == "PATCH" else None
        r = await app_http.request(metodo, ruta, headers=h, json=cuerpo)
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited", ruta
        assert int(r.headers["retry-after"]) >= 1
