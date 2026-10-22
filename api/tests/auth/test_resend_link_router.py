"""`POST /api/v1/users/{user_id}/resend-link` por HTTP (S2-B4; US-052; L-13, US-018).

Solo admin (coach y socio 403, sin token 401); 200 `IssuedLinkOut` (`url`, `purpose`,
`expires_at`) con `Cache-Control: no-store` (la respuesta lleva el enlace y nunca se cachea);
`url` sale de `FRONT_BASE_URL` de `request.app.state.settings`. Id inexistente 404
`user_not_found`, id mal formado 422, bloqueado o la propia cuenta 409 `user_not_eligible`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_opaque_token
from app.modules.auth.models import OneTimeToken
from tests.conftest import T0, Cabeceras, CrearUsuario


def _ruta(user_id: object) -> str:
    return f"/api/v1/users/{user_id}/resend-link"


async def test_el_admin_recibe_el_enlace_sin_cache(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    api_prueba.state.settings = api_prueba.state.settings.model_copy(
        update={"FRONT_BASE_URL": "http://localhost:8180/"}
    )
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    r = await app_http.post(_ruta(pendiente.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    datos = r.json()
    assert set(datos) == {"url", "purpose", "expires_at"}
    assert datos["purpose"] == "activate"
    assert datetime.fromisoformat(datos["expires_at"]) == T0 + timedelta(hours=72)
    prefijo = "http://localhost:8180/restablecer/"
    assert datos["url"].startswith(prefijo)
    token = datos["url"].removeprefix(prefijo)
    fila = await session.scalar(
        select(OneTimeToken).where(OneTimeToken.token_hash == hash_opaque_token(token))
    )
    assert fila is not None and fila.user_id == pendiente.id
    assert "set-cookie" not in r.headers


async def test_un_coach_activo_recibe_reset(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.post(_ruta(coach.id), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "reset"
    assert datetime.fromisoformat(r.json()["expires_at"]) == T0 + timedelta(hours=1)


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    rol: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    usuario = await usuario_real(rol)
    otro = await usuario_real("coach", password=None)
    r = await app_http.post(_ruta(otro.id), headers=cabeceras(usuario))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_sin_token_da_401(app_http: AsyncClient, usuario_real: CrearUsuario) -> None:
    otro = await usuario_real("coach", password=None)
    r = await app_http.post(_ruta(otro.id))
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(_ruta(uuid4()), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_un_id_mal_formado_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(_ruta("no-es-uuid"), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


async def test_la_propia_cuenta_y_un_bloqueado_dan_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    for objetivo in (admin.id, bloqueado.id):
        r = await app_http.post(_ruta(objetivo), headers=cabeceras(admin))
        assert r.status_code == 409, (objetivo, r.text)
        assert r.json()["error"]["code"] == "user_not_eligible"


async def test_dos_reenvios_dan_enlaces_distintos_y_solo_el_ultimo_sirve(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    primero = await app_http.post(_ruta(coach.id), headers=cabeceras(admin))
    segundo = await app_http.post(_ruta(coach.id), headers=cabeceras(admin))
    assert primero.status_code == segundo.status_code == 200
    assert primero.json()["url"] != segundo.json()["url"]
    token_viejo = primero.json()["url"].rsplit("/", 1)[-1]
    r = await app_http.post(
        "/api/v1/auth/reset", json={"token": token_viejo, "new_password": "Mandarina-Solar-58q"}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"
