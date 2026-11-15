"""Modo quiosco del lado del servidor (S7-C4, S7-D41; revisión de F4: HIGH-1, MEDIUM-1, MEDIUM-2).

- `POST /auth/kiosk`: marca la sesión del refresh con `kiosk_path` y entrega un access con la
  marca (`kiosk=true`); la marca sobrevive a la rotación del refresh y muere con el logout.
- `POST /auth/kiosk/exit`: verifica la contraseña SIN crear sesión ni rotar el refresh, y SIN
  sumar al bloqueo de la cuenta; sus fallos tienen tope propio por usuario (5 cada 15 min, 429).
- `GET /auth/me` trae `kiosk_path`.
- Con la marca, las rutas que revelan datos cifrados dan 403 `kiosk_mode`; sin ella funcionan.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import create_access_token, decode_access_token, hash_opaque_token
from app.modules.auth.models import RefreshToken, User
from tests.auth._sesion import LOGIN, LOGOUT, ORIGEN, REFRESH, cookie_de, post_auth, set_cookie
from tests.conftest import CLAVE_PRUEBA, CrearUsuario, UsuarioPrueba

KIOSK = "/api/v1/auth/kiosk"
SALIR = "/api/v1/auth/kiosk/exit"
ME = "/api/v1/auth/me"
RUTA = f"/clases/{uuid4()}/checkin"
MALA = "otra-clave-9876"


async def _entrar(cliente: AsyncClient, usuario: UsuarioPrueba) -> tuple[str, str]:
    r = await post_auth(cliente, LOGIN, json={"email": usuario.email, "password": CLAVE_PRUEBA})
    assert r.status_code == 200, r.text
    refresh = cookie_de(r)
    assert refresh
    return r.json()["access_token"], refresh


async def _poner(cliente: AsyncClient, access: str, refresh: str, path: str = RUTA) -> Response:
    return await post_auth(
        cliente,
        KIOSK,
        cookie=refresh,
        json={"path": path},
        headers={"Authorization": f"Bearer {access}"},
    )


async def _salir(
    cliente: AsyncClient, access: str, refresh: str, password: str = CLAVE_PRUEBA
) -> Response:
    return await post_auth(
        cliente,
        SALIR,
        cookie=refresh,
        json={"password": password},
        headers={"Authorization": f"Bearer {access}"},
    )


async def _me(cliente: AsyncClient, access: str, refresh: str | None) -> Response:
    cliente.cookies.clear()
    cabeceras = {"Authorization": f"Bearer {access}", "Origin": ORIGEN}
    if refresh is not None:
        cabeceras["Cookie"] = f"apex_refresh={refresh}"
    return await cliente.get(ME, headers=cabeceras)


async def _fila(session: AsyncSession, refresh: str) -> RefreshToken:
    fila = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_opaque_token(refresh))
        .execution_options(populate_existing=True)
    )
    assert fila is not None
    return fila


async def _total_refresh(session: AsyncSession, user_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user_id)
    )
    return int(total or 0)


# Entrada ------------------------------------------------------------------------------------


async def test_entrar_marca_la_sesion_y_entrega_un_access_con_la_marca(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    r = await _poner(app_http, access, refresh)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["kiosk_path"] == RUTA
    assert decode_access_token(r.json()["access_token"], reloj).kiosk is True
    assert (await _fila(session, refresh)).kiosk_path == RUTA


@pytest.mark.parametrize(
    "path",
    [
        "/clases/no-es-uuid/checkin",
        "/panel",
        "https://evil.example/clases/00000000-0000-0000-0000-000000000000/checkin",
        f"/clases/{uuid4()}/checkin/../../panel",
        f"//evil.example/clases/{uuid4()}/checkin",
        "",
    ],
)
async def test_entrar_rechaza_una_ruta_que_no_es_el_checkin(
    app_http: AsyncClient, usuario_real: CrearUsuario, path: str
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    r = await _poner(app_http, access, refresh, path)
    assert r.status_code == 422, r.text


async def test_entrar_sin_cookie_es_401_origen_ajeno_403_y_un_socio_403(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    sin = await post_auth(
        app_http, KIOSK, json={"path": RUTA}, headers={"Authorization": f"Bearer {access}"}
    )
    assert sin.status_code == 401 and sin.json()["error"]["code"] == "invalid_refresh"
    ajeno = await post_auth(
        app_http,
        KIOSK,
        cookie=refresh,
        origin="http://evil.example",
        json={"path": RUTA},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert ajeno.status_code == 403
    socio = await usuario_real("member", member_id=uuid4())
    acceso_socio, refresh_socio = await _entrar(app_http, socio)
    r = await _poner(app_http, acceso_socio, refresh_socio)
    assert r.status_code == 403


# La marca sobrevive a la rotación y se ve en /auth/me ---------------------------------------


async def test_la_marca_sobrevive_a_la_rotacion_del_refresh(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    assert (await _me(app_http, access, refresh)).json()["kiosk_path"] is None
    assert (await _poner(app_http, access, refresh)).status_code == 200
    reloj.advance(minutes=14)
    r = await post_auth(app_http, REFRESH, cookie=refresh)
    assert r.status_code == 200, r.text
    nuevo = cookie_de(r)
    assert nuevo and nuevo != refresh
    assert (await _fila(session, nuevo)).kiosk_path == RUTA
    assert decode_access_token(r.json()["access_token"], reloj).kiosk is True
    me = await _me(app_http, r.json()["access_token"], nuevo)
    assert me.status_code == 200 and me.json()["kiosk_path"] == RUTA


async def test_sin_marca_el_refresh_no_inventa_una(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    _, refresh = await _entrar(app_http, coach)
    r = await post_auth(app_http, REFRESH, cookie=refresh)
    assert decode_access_token(r.json()["access_token"], reloj).kiosk is False


# Salida: sin sesión nueva, sin rotar, sin bloqueo -------------------------------------------


async def test_salir_con_la_contrasena_limpia_la_marca_sin_crear_sesion_ni_rotar(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    entrada = await _poner(app_http, access, refresh)
    antes = await _total_refresh(session, coach.id)
    r = await _salir(app_http, entrada.json()["access_token"], refresh)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["kiosk_path"] is None
    assert decode_access_token(r.json()["access_token"], reloj).kiosk is False
    assert set_cookie(r) == ""  # no rota ni borra la cookie
    assert await _total_refresh(session, coach.id) == antes
    fila = await _fila(session, refresh)
    assert fila.kiosk_path is None and fila.revoked_at is None and fila.replaced_by_id is None
    me = await _me(app_http, r.json()["access_token"], refresh)
    assert me.json()["kiosk_path"] is None


async def test_salir_con_contrasena_errada_es_401_sin_sumar_al_bloqueo(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    entrada = await _poner(app_http, access, refresh)
    for _ in range(5):
        r = await _salir(app_http, entrada.json()["access_token"], refresh, MALA)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_password"
        assert MALA not in r.text
    usuario = await session.scalar(
        select(User).where(User.id == coach.id).execution_options(populate_existing=True)
    )
    assert usuario is not None
    assert usuario.failed_login_count == 0 and usuario.locked_at is None
    assert (await _fila(session, refresh)).kiosk_path == RUTA  # la marca sigue


async def test_los_fallos_de_salida_tienen_un_429_propio_por_usuario(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    token = (await _poner(app_http, access, refresh)).json()["access_token"]
    for _ in range(5):
        assert (await _salir(app_http, token, refresh, MALA)).status_code == 401
    r = await _salir(app_http, token, refresh, CLAVE_PRUEBA)  # aun correcta: tope agotado
    assert r.status_code == 429 and "retry-after" in r.headers
    assert (await _fila(session, refresh)).kiosk_path == RUTA
    access_o, refresh_o = await _entrar(app_http, otro)  # el tope es por usuario
    token_o = (await _poner(app_http, access_o, refresh_o)).json()["access_token"]
    assert (await _salir(app_http, token_o, refresh_o)).status_code == 200


async def test_salir_exige_cookie_origen_y_cuerpo(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    cabecera = {"Authorization": f"Bearer {access}"}
    sin = await post_auth(app_http, SALIR, json={"password": CLAVE_PRUEBA}, headers=cabecera)
    assert sin.status_code == 401
    ajeno = await post_auth(
        app_http,
        SALIR,
        cookie=refresh,
        origin="http://evil.example",
        json={"password": CLAVE_PRUEBA},
        headers=cabecera,
    )
    assert ajeno.status_code == 403
    vacio = await post_auth(app_http, SALIR, cookie=refresh, json={}, headers=cabecera)
    assert vacio.status_code == 422


# Logout -------------------------------------------------------------------------------------


async def test_el_logout_borra_la_marca(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    await _poner(app_http, access, refresh)
    r = await post_auth(app_http, LOGOUT, cookie=refresh)
    assert r.status_code == 204
    fila = await _fila(session, refresh)
    assert fila.revoked_at is not None and fila.kiosk_path is None


# Rutas bloqueadas ---------------------------------------------------------------------------


async def test_con_la_marca_revelar_da_403_kiosk_mode_y_sin_ella_funciona(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    ruta = f"/api/v1/members/{uuid4()}/reveal"
    cuerpo = {"field": "phone"}
    normal = await app_http.post(
        ruta, json=cuerpo, headers={"Authorization": f"Bearer {coach.token}", "Origin": ORIGEN}
    )
    assert normal.status_code == 404, normal.text  # llega al service: el socio no existe
    kiosk = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    r = await app_http.post(
        ruta, json=cuerpo, headers={"Authorization": f"Bearer {kiosk}", "Origin": ORIGEN}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode", r.text


async def test_con_la_marca_las_rutas_del_checkin_siguen_abiertas(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    kiosk = create_access_token(coach.id, "coach", None, reloj, kiosk=True)
    r = await app_http.get(ME, headers={"Authorization": f"Bearer {kiosk}", "Origin": ORIGEN})
    assert r.status_code == 200, r.text
