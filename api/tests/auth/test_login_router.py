"""`POST /api/v1/auth/login` por HTTP (S2-B2; US-042; L-8, M-1, L-5, US-036 y M-2 del Sprint 1).

Cliente `app_http` sobre la sesión de la prueba; reloj en `T0`; piso de duración anulado.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_opaque_token
from app.modules.auth.models import RefreshToken
from tests.auth._sesion import (
    LOGIN,
    ORIGEN,
    ORIGEN_AJENO,
    EspiaArgon2,
    cookie_de,
    post_auth,
    set_cookie,
)
from tests.conftest import CLAVE_PRUEBA, ClienteDesde, CrearUsuario

ERRADA = "Otra-Clave-Distinta-77"


def _cuerpo(email: str, password: str = CLAVE_PRUEBA) -> dict[str, str]:
    return {"email": email, "password": password}


async def test_login_correcto_200_cookie_httponly_y_cuerpo_sin_refresh(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {
        "access_token",
        "token_type",
        "expires_in",
        "user",
        "must_change_password",
    }
    assert cuerpo["token_type"] == "bearer"  # noqa: S105 - tipo de token
    assert cuerpo["expires_in"] == 900
    assert cuerpo["user"] == {"id": str(coach.id), "email": coach.email, "role": "coach"}
    assert cuerpo["must_change_password"] is False
    assert r.headers["cache-control"] == "no-store"
    refresh = cookie_de(r)
    assert refresh and refresh not in r.text  # el refresh solo viaja en la cookie
    galleta = set_cookie(r).lower()
    assert "httponly" in galleta and "samesite=strict" in galleta
    assert "path=/api/v1/auth" in galleta and "max-age=604800" in galleta
    assert "secure" not in galleta  # COOKIE_SECURE=false en `settings_prueba`
    fila = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_opaque_token(refresh))
    )
    assert fila is not None and fila.user_id == coach.id


async def test_el_access_del_login_abre_una_ruta_protegida(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(admin.email))
    token = r.json()["access_token"]
    protegida = await app_http.get(
        "/api/v1/settings/gym", headers={"Authorization": f"Bearer {token}"}
    )
    assert protegida.status_code == 200


async def test_con_cookie_secure_la_cookie_lleva_secure(
    api_prueba: FastAPI, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    """L-8: `Secure` sale de `COOKIE_SECURE` de la `Settings` de la app."""
    api_prueba.state.settings = api_prueba.state.settings.model_copy(update={"COOKIE_SECURE": True})
    coach = await usuario_real("coach")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email))
    assert r.status_code == 200
    assert "secure" in set_cookie(r).lower()


async def test_correo_con_espacios_y_mayusculas_entra(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    await usuario_real("coach", email="coach@test.apex")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(" Coach@Test.Apex "))
    assert r.status_code == 200 and r.json()["user"]["email"] == "coach@test.apex"


async def test_las_cinco_causas_de_rechazo_dan_el_mismo_401(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    bloqueado = await usuario_real("coach", bloqueado=True)
    inactivo = await usuario_real("coach", activo=False)
    pendiente = await usuario_real("coach", password=None)
    intentos = [
        _cuerpo("nadie@test.apex"),
        _cuerpo(coach.email, ERRADA),
        _cuerpo(bloqueado.email),
        _cuerpo(inactivo.email),
        _cuerpo(pendiente.email),
    ]
    respuestas = [await post_auth(app_http, LOGIN, json=c) for c in intentos]
    assert {r.status_code for r in respuestas} == {401}
    assert {r.text for r in respuestas} == {
        '{"error":{"code":"invalid_credentials","message":"Correo o contraseña incorrectos."}}'
    }
    assert all(r.headers["www-authenticate"] == "Bearer" for r in respuestas)
    assert all(cookie_de(r) is None for r in respuestas)


@pytest.mark.parametrize(
    "cuerpo",
    [{"password": CLAVE_PRUEBA}, {"email": "sin-arroba", "password": CLAVE_PRUEBA}],
    ids=["sin-email", "email-mal-formado"],
)
async def test_email_ausente_o_mal_formado_da_422_con_field(
    app_http: AsyncClient, cuerpo: dict[str, str]
) -> None:
    r = await post_auth(app_http, LOGIN, json=cuerpo)
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "email"
    assert "sin-arroba" not in r.text


async def test_contrasena_de_129_da_422_con_field_password(
    app_http: AsyncClient, usuario_real: CrearUsuario, espia_argon2: EspiaArgon2
) -> None:
    """L-5 y S2-D30: `max_length=128`; ni se evalúa argon2 ni se repite el valor."""
    coach = await usuario_real("coach")
    espia_argon2.reiniciar()
    larga = "casa-azul-19" + "y" * 117
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email, larga))
    assert r.status_code == 422 and r.json()["error"]["field"] == "password"
    assert larga not in r.text
    assert espia_argon2.total == 0


async def test_origin_ajeno_da_403_sin_cookie(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    """M-1 (S2-D38): login CSRF; sin tocar la cookie."""
    coach = await usuario_real("coach")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email), origin=ORIGEN_AJENO)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert set_cookie(r) == ""


async def test_sin_origin_ni_referer_ni_sec_fetch_site_da_403(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email), origin=None)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    "cabeceras",
    [
        {"Referer": f"{ORIGEN}/login?next=/socios"},
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "none"},
    ],
    ids=["referer", "sec-fetch-same-origin", "sec-fetch-none"],
)
async def test_referer_o_sec_fetch_site_reemplazan_al_origin(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: dict[str, str]
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email), origin=None, headers=cabeceras)
    assert r.status_code == 200, r.text


async def test_sec_fetch_site_cross_site_da_403(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(
        app_http,
        LOGIN,
        json=_cuerpo(coach.email),
        origin=None,
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403


async def test_auth_allowed_origins_reemplaza_al_origen_del_front(
    api_prueba: FastAPI, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    api_prueba.state.settings = api_prueba.state.settings.model_copy(
        update={"AUTH_ALLOWED_ORIGINS": ["http://localhost:5173"]}
    )
    coach = await usuario_real("coach")
    vite = await post_auth(
        app_http, LOGIN, json=_cuerpo(coach.email), origin="http://localhost:5173"
    )
    assert vite.status_code == 200
    front = await post_auth(app_http, LOGIN, json=_cuerpo(coach.email), origin=ORIGEN)
    assert front.status_code == 403


async def test_el_sexto_intento_por_ip_da_429_sin_evaluar_la_contrasena(
    app_http: AsyncClient, espia_argon2: EspiaArgon2
) -> None:
    """US-036 con `LOGIN_IP_LIMIT=5` por `LOGIN_IP_WINDOW_S=60` (E5)."""
    for _ in range(5):
        assert (
            await post_auth(app_http, LOGIN, json=_cuerpo("nadie@test.apex"))
        ).status_code == 401
    espia_argon2.reiniciar()
    r = await post_auth(app_http, LOGIN, json=_cuerpo("nadie@test.apex"))
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert espia_argon2.total == 0


async def test_dos_ipv6_del_mismo_64_comparten_el_cupo(cliente_desde: ClienteDesde) -> None:
    primera = cliente_desde("2001:db8:1:2::1")
    vecina = cliente_desde("2001:db8:1:2::ffff")
    otra_red = cliente_desde("2001:db8:1:3::1")
    for _ in range(5):
        assert (await post_auth(primera, LOGIN, json=_cuerpo("nadie@test.apex"))).status_code == 401
    assert (await post_auth(vecina, LOGIN, json=_cuerpo("nadie@test.apex"))).status_code == 429
    assert (await post_auth(otra_red, LOGIN, json=_cuerpo("nadie@test.apex"))).status_code == 401
