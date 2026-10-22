"""`POST /api/v1/auth/logout` por HTTP (S2-B2; US-044; H-1 / S2-D35, M-1, L-12).

El logout se autentica por la cookie, no por el Bearer: con el access vencido igual revoca el
refresh de la cookie, responde 204 y borra la cookie.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import hash_opaque_token
from app.modules.auth.models import RefreshToken
from tests.auth._sesion import (
    LOGIN,
    LOGOUT,
    ORIGEN_AJENO,
    REFRESH,
    cookie_de,
    post_auth,
    set_cookie,
)
from tests.conftest import CLAVE_PRUEBA, CrearUsuario, UsuarioPrueba


async def _entrar(cliente: AsyncClient, usuario: UsuarioPrueba) -> tuple[str, str]:
    r = await post_auth(cliente, LOGIN, json={"email": usuario.email, "password": CLAVE_PRUEBA})
    assert r.status_code == 200, r.text
    refresh = cookie_de(r)
    assert refresh
    return r.json()["access_token"], refresh


async def _fila(session: AsyncSession, token: str) -> RefreshToken:
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(token))
        .execution_options(populate_existing=True)
    )
    assert fila is not None
    return fila


def _borra_la_cookie(cabecera: str) -> bool:
    baja = cabecera.lower()
    return (
        (baja.startswith('apex_refresh=""') or baja.startswith("apex_refresh=;"))
        and "max-age=0" in baja
        and "path=/api/v1/auth" in baja
    )


async def test_con_el_access_vencido_y_la_cookie_valida_revoca_y_borra(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    """H-1: la tableta del gimnasio tras más de 15 minutos; el siguiente no hereda la sesión."""
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    _, otra = await _entrar(app_http, coach)  # otra sesión del mismo usuario
    reloj.advance(minutes=16)
    r = await post_auth(
        app_http, LOGOUT, cookie=refresh, headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 204 and r.content == b""
    assert _borra_la_cookie(set_cookie(r)), set_cookie(r)
    fila = await _fila(session, refresh)
    assert fila.revoked_at is not None and fila.replaced_by_id is None
    despues = await post_auth(app_http, REFRESH, cookie=refresh)
    assert despues.status_code == 401 and despues.json()["error"]["code"] == "invalid_refresh"
    assert (await _fila(session, otra)).revoked_at is None  # no fue reuso: la otra sigue viva


async def test_sin_cookie_y_sin_access_da_204_y_borra(app_http: AsyncClient) -> None:
    r = await post_auth(app_http, LOGOUT)
    assert r.status_code == 204
    assert _borra_la_cookie(set_cookie(r))


async def test_cookie_desconocida_da_204_y_borra(app_http: AsyncClient) -> None:
    r = await post_auth(app_http, LOGOUT, cookie="no-existe-este-token")
    assert r.status_code == 204
    assert _borra_la_cookie(set_cookie(r))


async def test_origin_ajeno_da_403_sin_tocar_la_cookie(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    _, refresh = await _entrar(app_http, coach)
    r = await post_auth(app_http, LOGOUT, cookie=refresh, origin=ORIGEN_AJENO)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert set_cookie(r) == ""
    assert (await _fila(session, refresh)).revoked_at is None


async def test_logout_tiene_su_propio_limite_por_ip(app_http: AsyncClient) -> None:
    """L-12: `rate_limit("logout")` con `LOGOUT_IP_LIMIT=30` por minuto."""
    for _ in range(30):
        assert (await post_auth(app_http, LOGOUT)).status_code == 204
    r = await post_auth(app_http, LOGOUT)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
