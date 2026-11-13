"""La cookie del refresh en los dos modos de despliegue (S6-E1, US-153 criterio 7; D28).

Con `APEX_DOMAIN` la cookie lleva `Secure`; en modo LAN no. `SameSite=Strict` en ambos. La app real
(`api_prueba`) lee `app.state.settings`, que cada prueba reemplaza por la `Settings` del modo.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Response
from httpx import AsyncClient

from app.core.config import Settings
from tests.auth._sesion import LOGIN, REFRESH, cookie_de, post_auth, set_cookie
from tests.conftest import (
    CLAVE_PRUEBA,
    ORIGEN_DOMINIO_PRUEBA,
    CrearUsuario,
    SettingsDeModo,
)

ORIGEN_LAN = "http://localhost"


def _atributos(cabecera: str) -> set[str]:
    """Los atributos de `Set-Cookie` en minúsculas y sin valor (`secure`, `httponly`, ...)."""
    return {parte.strip().split("=", 1)[0].lower() for parte in cabecera.split(";")}


def _modo(api: FastAPI, settings_prueba: Settings, ajustes: Settings) -> None:
    api.state.settings = ajustes.model_copy(update={"DATABASE_URL": settings_prueba.DATABASE_URL})


@pytest.fixture
def con_dominio(
    api_prueba: FastAPI, settings_prueba: Settings, settings_dominio: SettingsDeModo
) -> str:
    _modo(api_prueba, settings_prueba, settings_dominio(settings_prueba))
    return ORIGEN_DOMINIO_PRUEBA


@pytest.fixture
def en_lan(api_prueba: FastAPI, settings_prueba: Settings, settings_lan: SettingsDeModo) -> str:
    _modo(api_prueba, settings_prueba, settings_lan(settings_prueba))
    return ORIGEN_LAN


async def _login(cliente: AsyncClient, usuario_real: CrearUsuario, origen: str) -> str:
    usuario = await usuario_real("coach")
    r = await post_auth(
        cliente, LOGIN, origin=origen, json={"email": usuario.email, "password": CLAVE_PRUEBA}
    )
    assert r.status_code == 200, r.text
    return set_cookie(r)


async def test_el_login_con_dominio_pone_secure_y_samesite_strict(
    app_http: AsyncClient, usuario_real: CrearUsuario, con_dominio: str
) -> None:
    atributos = _atributos(await _login(app_http, usuario_real, con_dominio))
    assert "secure" in atributos
    assert "samesite" in atributos


async def test_el_login_sin_dominio_no_pone_secure_y_si_samesite_strict(
    app_http: AsyncClient, usuario_real: CrearUsuario, en_lan: str
) -> None:
    cabecera = await _login(app_http, usuario_real, en_lan)
    assert "secure" not in _atributos(cabecera)
    assert "samesite=strict" in cabecera.lower()


async def test_el_login_con_dominio_conserva_samesite_strict(
    app_http: AsyncClient, usuario_real: CrearUsuario, con_dominio: str
) -> None:
    assert "samesite=strict" in (await _login(app_http, usuario_real, con_dominio)).lower()


async def _refrescar(
    cliente: AsyncClient, usuario_real: CrearUsuario, origen: str
) -> tuple[str, str]:
    usuario = await usuario_real("coach")
    entrada = await post_auth(
        cliente, LOGIN, origin=origen, json={"email": usuario.email, "password": CLAVE_PRUEBA}
    )
    assert entrada.status_code == 200, entrada.text
    refresco = cookie_de(entrada)
    assert refresco
    r = await post_auth(cliente, REFRESH, origin=origen, cookie=refresco)
    assert r.status_code == 200, r.text
    return set_cookie(r), refresco


async def test_el_refresh_con_dominio_rota_la_cookie_con_secure_y_samesite_strict(
    app_http: AsyncClient, usuario_real: CrearUsuario, con_dominio: str
) -> None:
    cabecera, _ = await _refrescar(app_http, usuario_real, con_dominio)
    assert "secure" in _atributos(cabecera)
    assert "samesite=strict" in cabecera.lower()


async def test_el_refresh_sin_dominio_rota_la_cookie_sin_secure_y_con_samesite_strict(
    app_http: AsyncClient, usuario_real: CrearUsuario, en_lan: str
) -> None:
    cabecera, _ = await _refrescar(app_http, usuario_real, en_lan)
    assert "secure" not in _atributos(cabecera)
    assert "samesite=strict" in cabecera.lower()


async def test_el_refresh_fallido_con_dominio_borra_la_cookie_con_secure(
    app_http: AsyncClient, con_dominio: str
) -> None:
    r = await post_auth(app_http, REFRESH, origin=con_dominio, cookie="inexistente")
    assert r.status_code == 401
    cabecera = set_cookie(r)
    assert "max-age=0" in cabecera.lower()
    assert "secure" in _atributos(cabecera)


async def test_el_refresh_fallido_sin_dominio_borra_la_cookie_sin_secure(
    app_http: AsyncClient, en_lan: str
) -> None:
    r = await post_auth(app_http, REFRESH, origin=en_lan, cookie="inexistente")
    assert r.status_code == 401
    cabecera = set_cookie(r)
    assert "max-age=0" in cabecera.lower()
    assert "secure" not in _atributos(cabecera)


def test_la_cookie_pasa_por_cookie_secure_al_ponerse(
    monkeypatch: pytest.MonkeyPatch, settings_lan: SettingsDeModo
) -> None:
    """El atributo `Secure` sale de `cookie_secure(settings)` (S6-E1), no de `COOKIE_SECURE`."""
    from app.modules.auth import cookies

    monkeypatch.setattr(cookies, "cookie_secure", lambda _settings: True)
    respuesta = Response()
    cookies.set_refresh_cookie(respuesta, "token-de-prueba", settings_lan(COOKIE_SECURE=False))
    assert "secure" in _atributos(respuesta.headers["set-cookie"])


def test_la_cookie_pasa_por_cookie_secure_al_borrarse(
    monkeypatch: pytest.MonkeyPatch, settings_lan: SettingsDeModo
) -> None:
    from app.modules.auth import cookies

    monkeypatch.setattr(cookies, "cookie_secure", lambda _settings: True)
    cabecera = cookies.clear_cookie_header(settings_lan(COOKIE_SECURE=False))
    assert "secure" in _atributos(cabecera)
