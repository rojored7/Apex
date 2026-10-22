"""`POST /api/v1/users` por HTTP (S2-B3; US-047; L-2 / S2-D42, blueprint 7.2, US-018).

Solo admin; 201 `CreateUserOut` (`user`, `activation_url`, `expires_at`) con
`Cache-Control: no-store`. `activation_url` sale de `FRONT_BASE_URL` de
`request.app.state.settings` más `/restablecer/<token>`. `role` admite solo `admin` y `coach`
(`member` da 422, L-2) y el cuerpo no acepta `member_id` (`extra="forbid"`). Un correo tomado
da 409 `email_taken` con `field` y `existing_id`. El token solo se guarda como hash y ni el
token ni la URL llegan a los logs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_opaque_token
from app.modules.auth.models import OneTimeToken
from tests.auth._cuentas import CAMPOS_USER_OUT, USERS, etiqueta, fila_usuario
from tests.conftest import T0, Cabeceras, CrearUsuario


def _cuerpo(**cambios: Any) -> dict[str, Any]:
    return {"email": f"alta-{etiqueta()}@test.apex", "role": "coach", **cambios}


async def test_el_admin_crea_y_recibe_el_enlace_una_vez(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    api_prueba.state.settings = api_prueba.state.settings.model_copy(
        update={"FRONT_BASE_URL": "http://localhost:8180"}
    )
    admin = await usuario_real("admin")
    cuerpo = _cuerpo()
    r = await app_http.post(USERS, json=cuerpo, headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == {"user", "activation_url", "expires_at"}
    assert set(datos["user"]) == CAMPOS_USER_OUT
    assert datos["user"]["email"] == cuerpo["email"]
    assert datos["user"]["status"] == "pending_activation"
    assert datos["user"]["must_change_password"] is False
    assert datetime.fromisoformat(datos["expires_at"]) == T0 + timedelta(hours=72)
    prefijo = "http://localhost:8180/restablecer/"
    assert datos["activation_url"].startswith(prefijo)
    token = datos["activation_url"].removeprefix(prefijo)
    assert "password_hash" not in r.text

    fila = await session.scalar(
        select(OneTimeToken).where(OneTimeToken.token_hash == hash_opaque_token(token))
    )
    assert fila is not None and fila.purpose == "activate"
    assert str(fila.user_id) == datos["user"]["id"]
    assert (await fila_usuario(session, fila.user_id))["password_hash"] is None


async def test_la_url_usa_el_front_base_url_vigente(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """Con la `Settings` de las pruebas (`FRONT_BASE_URL=http://localhost`)."""
    admin = await usuario_real("admin")
    r = await app_http.post(USERS, json=_cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    assert r.json()["activation_url"].startswith("http://localhost/restablecer/")


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"role": "member"}, "role"),
        ({"role": "root"}, "role"),
        ({"member_id": str(uuid4())}, "member_id"),
        ({"email": "sin-arroba"}, "email"),
        ({"email": ""}, "email"),
    ],
    ids=["socio-L2", "rol-desconocido", "member-id", "correo-sin-arroba", "correo-vacio"],
)
async def test_cuerpo_invalido_da_422_con_el_campo(
    cambios: dict[str, Any],
    campo: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(USERS, json=_cuerpo(**cambios), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo


async def test_un_correo_tomado_da_409_con_el_id_existente(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    correo = f"tomado-{etiqueta()}@test.apex"
    existente = await usuario_real("coach", email=correo)
    r = await app_http.post(
        USERS, json=_cuerpo(email=f" {correo.upper()} "), headers=cabeceras(admin)
    )
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "email_taken"
    assert error["field"] == "email"
    assert error["existing_id"] == str(existente.id)


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    usuario = await usuario_real(rol)
    r = await app_http.post(USERS, json=_cuerpo(), headers=cabeceras(usuario))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.post(USERS, json=_cuerpo())
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_el_admin_que_debe_cambiar_la_contrasena_no_crea(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin", debe_cambiar=True)
    r = await app_http.post(USERS, json=_cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "password_change_required"


async def test_ni_el_token_ni_la_url_llegan_a_los_logs(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    caplog.set_level(logging.DEBUG)
    r = await app_http.post(USERS, json=_cuerpo(), headers=cabeceras(admin))
    assert r.status_code == 201, r.text
    url = r.json()["activation_url"]
    token = url.rsplit("/", 1)[-1]
    texto = caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    assert token not in texto
    assert url not in texto
