"""`POST /api/v1/auth/refresh` por HTTP (S2-B2; US-043; N-13, M-1, M-2, H-3, L-8, L-12).

Cliente `app_http` sobre la sesión de la prueba; reloj en `T0`; la cookie viaja a mano.
"""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import hash_opaque_token
from app.modules.auth.models import RefreshToken
from tests.auth._sesion import (
    LOGIN,
    ORIGEN_AJENO,
    REFRESH,
    cookie_de,
    post_auth,
    set_cookie,
)
from tests.conftest import CLAVE_PRUEBA, T0, CrearUsuario, UsuarioPrueba


async def _entrar(cliente: AsyncClient, usuario: UsuarioPrueba) -> tuple[str, str]:
    r = await post_auth(cliente, LOGIN, json={"email": usuario.email, "password": CLAVE_PRUEBA})
    assert r.status_code == 200, r.text
    refresh = cookie_de(r)
    assert refresh
    return r.json()["access_token"], refresh


def _borra_la_cookie(cabecera: str) -> bool:
    baja = cabecera.lower()
    return (
        (baja.startswith('apex_refresh=""') or baja.startswith("apex_refresh=;"))
        and "max-age=0" in baja
        and "path=/api/v1/auth" in baja
    )


async def test_refresh_con_cookie_da_un_access_nuevo_y_rota_la_cookie(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    _, viejo = await _entrar(app_http, coach)
    reloj.advance(minutes=14)
    r = await post_auth(app_http, REFRESH, cookie=viejo)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"access_token", "token_type", "expires_in"}
    assert r.json()["token_type"] == "bearer"  # noqa: S105 - tipo de token
    assert r.json()["expires_in"] == 900
    assert r.headers["cache-control"] == "no-store"
    nuevo = cookie_de(r)
    assert nuevo and nuevo != viejo and nuevo not in r.text
    galleta = set_cookie(r).lower()
    assert "httponly" in galleta and "samesite=strict" in galleta
    assert "path=/api/v1/auth" in galleta and "max-age=604800" in galleta
    anterior = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(viejo))
        .execution_options(populate_existing=True)
    )
    assert anterior is not None and anterior.replaced_by_id is not None


async def test_sin_cookie_401_invalid_refresh_borra_la_cookie_e_ignora_el_cuerpo(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    _, refresh = await _entrar(app_http, coach)
    r = await post_auth(app_http, REFRESH, json={"refresh_token": refresh})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh"
    assert _borra_la_cookie(set_cookie(r)), set_cookie(r)


async def test_cookie_invalida_401_y_la_cookie_se_borra_con_los_mismos_atributos(
    app_http: AsyncClient,
) -> None:
    r = await post_auth(app_http, REFRESH, cookie="no-existe-este-token")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh"
    galleta = set_cookie(r)
    assert _borra_la_cookie(galleta), galleta
    assert "httponly" in galleta.lower() and "samesite=strict" in galleta.lower()


async def test_origin_ajeno_da_403_y_no_rota(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    """M-1: un `refresh` forzado desde otro origen del mismo sitio no rota ni borra."""
    coach = await usuario_real("coach")
    _, refresh = await _entrar(app_http, coach)
    r = await post_auth(app_http, REFRESH, cookie=refresh, origin=ORIGEN_AJENO)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert set_cookie(r) == ""
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(refresh))
        .execution_options(populate_existing=True)
    )
    assert fila is not None and fila.revoked_at is None and fila.replaced_by_id is None


async def test_access_vencido_da_token_expired_y_el_refresh_lo_renueva(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    access, refresh = await _entrar(app_http, admin)
    reloj.advance(minutes=16)  # 15 min de vida + 30 s de tolerancia ya pasaron
    vencido = await app_http.get(
        "/api/v1/settings/gym", headers={"Authorization": f"Bearer {access}"}
    )
    assert vencido.status_code == 401 and vencido.json()["error"]["code"] == "token_expired"
    r = await post_auth(app_http, REFRESH, cookie=refresh)
    assert r.status_code == 200
    nuevo = r.json()["access_token"]
    ok = await app_http.get("/api/v1/settings/gym", headers={"Authorization": f"Bearer {nuevo}"})
    assert ok.status_code == 200


async def test_firma_invalida_da_unauthorized(app_http: AsyncClient) -> None:
    r = await app_http.get(
        "/api/v1/settings/gym", headers={"Authorization": "Bearer eyJhbGciOiJFZERTQSJ9.x.y"}
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_el_reuso_corta_tambien_los_access_ya_emitidos(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """H-3: el reuso fija `tokens_valid_after`; un access con `iat` anterior da 401
    `unauthorized` aunque no haya vencido."""
    admin = await usuario_real("admin")
    access, rotado = await _entrar(app_http, admin)
    assert (await post_auth(app_http, REFRESH, cookie=rotado)).status_code == 200
    reloj.set(T0 + timedelta(seconds=11))
    reuso = await post_auth(app_http, REFRESH, cookie=rotado)
    assert reuso.status_code == 401 and reuso.json()["error"]["code"] == "invalid_refresh"
    assert _borra_la_cookie(set_cookie(reuso))
    viejo = await app_http.get(
        "/api/v1/settings/gym", headers={"Authorization": f"Bearer {access}"}
    )
    assert viejo.status_code == 401 and viejo.json()["error"]["code"] == "unauthorized"


async def test_refresh_tiene_su_propio_limite_por_ip(app_http: AsyncClient) -> None:
    """L-12: `rate_limit("refresh")` con `REFRESH_IP_LIMIT=60` por minuto."""
    for _ in range(60):
        assert (await post_auth(app_http, REFRESH)).status_code == 401
    r = await post_auth(app_http, REFRESH)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_un_rotado_dentro_de_la_gracia_da_401_sin_borrar_la_cookie_nueva(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock, session: AsyncSession
) -> None:
    """Revisión de seguridad de B2 (MEDIUM-1, M-2): la petición concurrente que pierde no
    emite `Set-Cookie` de borrado; si no, el navegador tiraría la cookie que acaba de rotar."""
    coach = await usuario_real("coach")
    _, rotado = await _entrar(app_http, coach)
    rota = await post_auth(app_http, REFRESH, cookie=rotado)
    assert rota.status_code == 200
    sucesor = cookie_de(rota)
    assert sucesor
    reloj.set(T0 + timedelta(seconds=5))
    perdedora = await post_auth(app_http, REFRESH, cookie=rotado)
    assert perdedora.status_code == 401
    assert perdedora.json()["error"]["code"] == "invalid_refresh"
    assert set_cookie(perdedora) == ""
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(sucesor))
        .execution_options(populate_existing=True)
    )
    assert fila is not None and fila.revoked_at is None
    assert (await post_auth(app_http, REFRESH, cookie=sucesor)).status_code == 200
