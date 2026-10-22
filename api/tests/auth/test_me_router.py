"""`GET /api/v1/auth/me` y `POST /api/v1/auth/me/password` por HTTP (S2-B3; US-045, US-046;
S2-D14, S2-D37 / H-3, S2-D46, M-8, L-5).

- `GET /auth/me`: los tres roles, también con `must_change_password` (es una de las dos rutas
  exentas); trae `gym_name` de `settings.service.gym_name` (respaldo `"APEX"`) y
  `Cache-Control: no-store`.
- `POST /auth/me/password`: 200 `AccessTokenOut` con un access nuevo; el access anterior da
  401 `unauthorized` en la petición siguiente (por `tokens_valid_after`), el nuevo da 200, la
  sesión de la cookie sigue renovando y las demás no. El reloj avanza 1 s entre el login y el
  cambio (el corte se compara en segundos enteros). La respuesta no toca la cookie.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.security import decode_access_token
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import SectionKey
from tests.auth._cuentas import ME, NUEVA, PASSWORD, USERS, avanzar
from tests.auth._sesion import LOGIN, ORIGEN, REFRESH, cookie_de, post_auth, set_cookie
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario, UsuarioPrueba
from tests.settings._apoyo import GYM_OK


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Origin": ORIGEN}


async def _entrar(cliente: AsyncClient, usuario: UsuarioPrueba) -> tuple[str, str]:
    r = await post_auth(cliente, LOGIN, json={"email": usuario.email, "password": CLAVE_PRUEBA})
    assert r.status_code == 200, r.text
    refresh = cookie_de(r)
    assert refresh
    return r.json()["access_token"], refresh


async def _cambiar(
    cliente: AsyncClient,
    access: str,
    *,
    cookie: str | None = None,
    actual: str = CLAVE_PRUEBA,
    nueva: str = NUEVA,
    extra: dict[str, Any] | None = None,
) -> Response:
    cuerpo: dict[str, Any] = {"current_password": actual, "new_password": nueva, **(extra or {})}
    return await post_auth(
        cliente, PASSWORD, cookie=cookie, json=cuerpo, headers={"Authorization": f"Bearer {access}"}
    )


# GET /auth/me ------------------------------------------------------------------------------


async def test_me_del_coach_trae_sus_datos_y_el_nombre_por_defecto(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(ME, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "id": str(coach.id),
        "email": coach.email,
        "role": "coach",
        "member_id": None,
        "gym_name": "APEX",
        "must_change_password": False,
    }
    assert r.headers["cache-control"] == "no-store"


async def test_me_trae_el_nombre_guardado_en_configuracion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    with actor_scope(admin.id):
        await settings_service.update_section(session, SectionKey.gym, GYM_OK, 0, admin.id)
        await session.commit()
    coach = await usuario_real("coach")
    r = await app_http.get(ME, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert r.json()["gym_name"] == "CrossFit Envigado"


async def test_me_del_socio_lleva_su_ficha(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(ME, headers=cabeceras(socio))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["role"] == "member"
    assert cuerpo["member_id"] == str(socio.user.member_id)


async def test_con_must_change_password_me_da_200_y_users_da_403(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    """M-8: la cuenta que debe cambiar la contraseña solo ve "Mi cuenta"."""
    admin = await usuario_real("admin", debe_cambiar=True)
    me = await app_http.get(ME, headers=cabeceras(admin))
    assert me.status_code == 200, me.text
    assert me.json()["must_change_password"] is True
    lista = await app_http.get(USERS, headers=cabeceras(admin))
    assert lista.status_code == 403
    assert lista.json()["error"]["code"] == "password_change_required"
    assert lista.json()["error"]["message"] == "Debes cambiar tu contraseña para continuar."


async def test_me_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await app_http.get(ME)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


# POST /auth/me/password --------------------------------------------------------------------


async def test_cambiar_devuelve_200_con_un_access_nuevo_y_corta_el_anterior(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """H-3 / S2-D37: el access viejo (iat T0) < `tokens_valid_after` (T0 + 1 s) → 401; el nuevo
    (iat T0 + 1 s) pasa. La sesión de la cookie sigue viva: el refresh posterior da 200."""
    coach = await usuario_real("coach")
    viejo, refresh = await _entrar(app_http, coach)
    avanzar(reloj, 1)

    r = await _cambiar(app_http, viejo, cookie=refresh)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"access_token", "token_type", "expires_in"}
    assert cuerpo["token_type"] == "bearer"  # noqa: S105 - tipo de token
    assert cuerpo["expires_in"] == 900
    assert r.headers["cache-control"] == "no-store"
    assert set_cookie(r) == ""  # el cambio no rota ni borra la cookie
    nuevo = cuerpo["access_token"]
    assert decode_access_token(nuevo, reloj).iat == int(reloj.now_utc().timestamp())

    con_viejo = await app_http.get(ME, headers=_bearer(viejo))
    assert con_viejo.status_code == 401
    assert con_viejo.json()["error"]["code"] == "unauthorized"
    assert (await app_http.get(ME, headers=_bearer(nuevo))).status_code == 200

    renovado = await post_auth(app_http, REFRESH, cookie=refresh)
    assert renovado.status_code == 200, renovado.text


async def test_cambiar_revoca_las_otras_sesiones_y_la_clave_vieja_ya_no_entra(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    access, refresh = await _entrar(app_http, coach)
    _, otra = await _entrar(app_http, coach)
    avanzar(reloj, 1)
    assert (await _cambiar(app_http, access, cookie=refresh)).status_code == 200

    revocada = await post_auth(app_http, REFRESH, cookie=otra)
    assert revocada.status_code == 401
    assert revocada.json()["error"]["code"] == "invalid_refresh"
    vieja = await post_auth(app_http, LOGIN, json={"email": coach.email, "password": CLAVE_PRUEBA})
    assert vieja.status_code == 401
    nueva = await post_auth(app_http, LOGIN, json={"email": coach.email, "password": NUEVA})
    assert nueva.status_code == 200, nueva.text


async def test_cambiar_sin_cookie_tambien_responde_200(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    r = await _cambiar(app_http, coach.token)
    assert r.status_code == 200, r.text
    assert (await app_http.get(ME, headers=_bearer(r.json()["access_token"]))).status_code == 200


async def test_la_cuenta_que_debe_cambiar_puede_cambiar_y_queda_libre(
    app_http: AsyncClient, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """M-8: `POST /auth/me/password` es la otra ruta exenta; tras el cambio el admin ya usa
    `GET /users`."""
    admin = await usuario_real("admin", debe_cambiar=True)
    avanzar(reloj, 1)
    r = await _cambiar(app_http, admin.token)
    assert r.status_code == 200, r.text
    nuevo = r.json()["access_token"]
    me = await app_http.get(ME, headers=_bearer(nuevo))
    assert me.status_code == 200 and me.json()["must_change_password"] is False
    assert (await app_http.get(USERS, headers=_bearer(nuevo))).status_code == 200


async def test_la_actual_errada_da_422_invalid_current_password(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    r = await _cambiar(app_http, coach.token, actual="No-Es-La-Actual-1")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_current_password"
    assert error["field"] == "current_password"
    # Nada cambió: el access de antes sigue valiendo.
    assert (await app_http.get(ME, headers=_bearer(coach.token))).status_code == 200


async def test_una_nueva_de_once_caracteres_da_422_weak_password(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    r = await _cambiar(app_http, coach.token, nueva="Once-letra1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "weak_password"
    assert r.json()["error"]["field"] == "new_password"
    assert "Once-letra1" not in r.text


async def test_una_nueva_igual_a_la_actual_da_422_weak_password(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    r = await _cambiar(app_http, coach.token, nueva=CLAVE_PRUEBA)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "weak_password"
    assert r.json()["error"]["field"] == "new_password"


async def test_129_caracteres_dan_422_con_el_campo_y_sin_eco(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    """S2-D30: `max_length=128` en el schema; el 422 nombra el campo y no repite el valor."""
    coach = await usuario_real("coach")
    larga = ("Ab1-" * 33)[:129]
    r = await _cambiar(app_http, coach.token, nueva=larga)
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "new_password"
    assert larga not in r.text
    r = await _cambiar(app_http, coach.token, actual=larga)
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "current_password"


async def test_un_campo_de_mas_da_422(app_http: AsyncClient, usuario_real: CrearUsuario) -> None:
    coach = await usuario_real("coach")
    r = await _cambiar(app_http, coach.token, extra={"user_id": str(coach.id)})
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "user_id"


async def test_cambiar_sin_token_da_401(app_http: AsyncClient) -> None:
    r = await post_auth(
        app_http, PASSWORD, json={"current_password": CLAVE_PRUEBA, "new_password": NUEVA}
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
