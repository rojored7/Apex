"""Texto seguro y `offset` acotado en las rutas de auth (revisión de seguridad V10, N-2).

Un NUL en el correo llegaba a asyncpg y daba 500 (en `POST /auth/login`, ruta pública, sin el
piso de duración) y un `offset` fuera de int64 daba 500 en `GET /users`. Ahora `EmailAddress`
rechaza `Cc`/`Cf` y `PageParams.offset` tiene tope: 422 con `field` y sin repetir el valor.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.auth._sesion import LOGIN, post_auth
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario

USERS = "/api/v1/users"
CORREOS_MALOS = ["a\u0000@x.co", "a@x\u0000.co", "a\u200b@x.co", "\u202ea@x.co"]


@pytest.mark.parametrize("correo", CORREOS_MALOS, ids=["nul", "nul-dominio", "zwsp", "rlo"])
async def test_login_con_correo_con_nul_o_formato_da_422(
    app_http: AsyncClient, correo: str
) -> None:
    r = await post_auth(app_http, LOGIN, json={"email": correo, "password": CLAVE_PRUEBA})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == {
        "code": "validation_error",
        "message": "El campo email no es válido.",
        "field": "email",
    }


@pytest.mark.parametrize("correo", CORREOS_MALOS[:2], ids=["nul", "nul-dominio"])
async def test_crear_usuario_con_nul_en_el_correo_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, correo: str
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(
        USERS, headers=cabeceras(admin), json={"email": correo, "role": "coach"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "email"


async def test_editar_usuario_con_nul_en_el_correo_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.patch(
        f"{USERS}/{coach.id}", headers=cabeceras(admin), json={"email": "c\u0000@x.co"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "email"


async def test_offset_fuera_de_rango_en_users_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(
        USERS, headers=cabeceras(admin), params={"offset": "99999999999999999999"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "offset"
