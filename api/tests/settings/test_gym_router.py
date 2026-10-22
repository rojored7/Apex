"""`/settings/gym` con el api real (US-055 T3; S2-D15)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import API, GYM_OK

RUTA = f"{API}/settings/gym"


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def test_sin_fila_el_nombre_es_apex(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(RUTA, headers=cabeceras(admin))
    assert r.status_code == 200
    assert r.json()["value"]["name"] == "APEX" and r.json()["version"] == 0


async def test_admin_guarda_y_la_version_sube(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.patch(RUTA, headers=cabeceras(admin), json={"value": GYM_OK, "version": 0})
    assert r.status_code == 200 and r.json()["version"] == 1
    r = await app_http.patch(
        RUTA, headers=cabeceras(admin), json={"value": {**GYM_OK, "nit": "900123456"}, "version": 1}
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    leido = await app_http.get(RUTA, headers=cabeceras(admin))
    assert leido.json()["value"]["nit"] == "900123456" and leido.json()["version"] == 2


async def test_nombre_vacio_da_422_value_name(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.patch(
        RUTA, headers=cabeceras(admin), json={"value": {"name": ""}, "version": 0}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == "value.name"


async def test_correo_invalido_da_422_value_email_sin_repetirlo(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    correo = "no-es-un-correo-9931"
    r = await app_http.patch(
        RUTA, headers=cabeceras(admin), json={"value": {**GYM_OK, "email": correo}, "version": 0}
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "value.email"
    assert correo not in r.text


async def test_campo_viejo_legal_id_da_422(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.patch(
        RUTA,
        headers=cabeceras(admin),
        json={"value": {**GYM_OK, "legal_id": "901234567-8"}, "version": 0},
    )
    assert r.status_code == 422 and r.json()["error"]["field"] == "value.legal_id"


@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_recibe_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, metodo: str
) -> None:
    coach = await usuario_real("coach")
    cuerpo = {"value": GYM_OK, "version": 0} if metodo == "PATCH" else None
    r = await app_http.request(metodo, RUTA, headers=cabeceras(coach), json=cuerpo)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
