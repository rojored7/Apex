"""`GET /tv/today` con el api real (S8-C2, US-176; S8-D18, S8-D33, M-3, C5)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.context import actor_scope
from app.modules.settings import service as settings_service
from tests.conftest import Cabeceras, CrearUsuario
from tests.tv._apoyo import ORIGEN, URL, emitir_token, tablero

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CABECERA = "X-Device-Token"


async def _token(session: AsyncSession, usuario_real: CrearUsuario) -> tuple[str, object]:
    admin = await usuario_real("admin")
    return await emitir_token(session, admin.id), admin


async def test_200_con_token_y_forma_exacta(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    await tablero(session, 2)
    r = await app_http.get(URL, headers={CABECERA: token})
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {"date", "refresh_seconds", "wod", "leaderboard"}
    assert len(cuerpo["leaderboard"]) == 2 and cuerpo["leaderboard"][0]["position"] == 1


async def test_no_store(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    r = await app_http.get(URL, headers={CABECERA: token})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"


async def test_401_sin_cabecera(app_http: AsyncClient) -> None:
    r = await app_http.get(URL)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_401_con_query_token(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    r = await app_http.get(URL, params={"token": token})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_401_inventado_y_rotado_uniforme(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    viejo, admin = await _token(session, usuario_real)
    await emitir_token(session, admin.id)  # type: ignore[attr-defined]  # C5: rota el token
    rotado = await app_http.get(URL, headers={CABECERA: viejo})
    inventado = await app_http.get(URL, headers={CABECERA: "inventado"})
    sin = await app_http.get(URL)
    assert rotado.status_code == inventado.status_code == sin.status_code == 401
    assert rotado.json() == inventado.json() == sin.json()


async def test_401_tras_revocar(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, admin = await _token(session, usuario_real)
    with actor_scope(admin.id):  # type: ignore[attr-defined]
        await settings_service.revoke_tv_token(session, admin.id)  # type: ignore[attr-defined]
        await session.commit()
    r = await app_http.get(URL, headers={CABECERA: token})
    assert r.status_code == 401


async def test_13_fallos_dan_429_tv_fail(app_http: AsyncClient) -> None:
    """M-3: 12 intentos con token inválido dan 401 y el 13.º ya es 429 con `Retry-After`."""
    for _ in range(12):
        assert (await app_http.get(URL, headers={CABECERA: "malo"})).status_code == 401
    r = await app_http.get(URL, headers={CABECERA: "malo"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"


async def test_misma_ip_12_fallos_no_bloquean_la_tv_valida(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    for _ in range(12):
        assert (await app_http.get(URL, headers={CABECERA: "malo"})).status_code == 401
    assert (await app_http.get(URL, headers={CABECERA: token})).status_code == 200


async def test_token_valido_no_consulta_ni_suma_tv_fail(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    for _ in range(3):
        assert (await app_http.get(URL, headers={CABECERA: token})).status_code == 200
    clave = ratelimit.ip_bucket_key("127.0.0.1", ipv4_prefix=32)
    assert await ratelimit.usage("tv-fail", clave, window_s=60, kind="ip") == 0


async def test_31_validas_dan_429_tv(
    app_http: AsyncClient, session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    token, _ = await _token(session, usuario_real)
    for _ in range(30):
        assert (await app_http.get(URL, headers={CABECERA: token})).status_code == 200
    r = await app_http.get(URL, headers={CABECERA: token})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


async def test_authorization_y_cookies_ignoradas(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    token, admin = await _token(session, usuario_real)
    basura = {CABECERA: token, "Authorization": "Bearer basura"}
    app_http.cookies.set("apex_session", "x")
    r = await app_http.get(URL, headers=basura)
    assert r.status_code == 200
    # Un access válido de un usuario NO sustituye al token de dispositivo.
    solo_usuario = await app_http.get(URL, headers=cabeceras(admin))  # type: ignore[arg-type]
    assert solo_usuario.status_code == 401


async def test_preflight_cors_rechazado(app_http: AsyncClient) -> None:
    r = await app_http.options(
        URL,
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-device-token",
        },
    )
    assert r.status_code == 400
    assert "x-device-token" not in r.headers.get("access-control-allow-headers", "").lower()


def test_el_origen_de_prueba_es_https() -> None:
    assert ORIGEN.startswith("https://")
