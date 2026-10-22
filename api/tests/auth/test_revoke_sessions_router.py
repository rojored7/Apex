"""`POST /api/v1/users/{user_id}/revoke-sessions` por HTTP (S2-B5; US-051; H-3, S2-D37).

Solo admin (coach y socio 403, sin token 401). 200 `RevokeSessionsOut` (`{"revoked": n}`, también
0) con `Cache-Control: no-store` y sin `Set-Cookie`. Un access emitido antes de la revocación da
401 `unauthorized` en `GET /auth/me`; uno emitido después (mismo segundo del corte o más tarde)
da 200: el corte compara segundos enteros y un `iat` igual pasa (S2-D37). No bloquea la cuenta.
404 para el técnico, un inexistente o una borrada; 422 con un id mal formado.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID
from app.core.security import create_access_token
from tests.auth._ciclo import entrar, ruta, sesiones_vivas
from tests.auth._cuentas import ME, avanzar, fila_usuario
from tests.conftest import T0, Cabeceras, CrearUsuario

T1 = T0 + timedelta(seconds=1)


async def test_devuelve_cuantas_revoco_sin_cache(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    await entrar(session, coach)
    await entrar(session, coach)
    avanzar(reloj, 1)
    r = await app_http.post(ruta(coach.id, "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert "set-cookie" not in r.headers
    assert r.json() == {"revoked": 2}
    assert await sesiones_vivas(session, coach.id, T1) == 0
    fila = await fila_usuario(session, coach.id)
    assert fila["tokens_valid_after"] == T1
    assert fila["locked_at"] is None


async def test_sin_sesiones_devuelve_cero(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.post(ruta(coach.id, "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json() == {"revoked": 0}


async def test_access_anterior_da_401_y_posterior_200(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")  # su access sale en T0
    assert (await app_http.get(ME, headers=cabeceras(coach))).status_code == 200
    avanzar(reloj, 1)
    r = await app_http.post(ruta(coach.id, "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text

    anterior = await app_http.get(ME, headers=cabeceras(coach))
    assert anterior.status_code == 401, anterior.text
    assert anterior.json()["error"]["code"] == "unauthorized"

    mismo_segundo = create_access_token(coach.id, "coach", None, reloj)  # iat = T1 = corte
    r = await app_http.get(ME, headers={"Authorization": f"Bearer {mismo_segundo}"})
    assert r.status_code == 200, r.text
    avanzar(reloj, 1)
    posterior = create_access_token(coach.id, "coach", None, reloj)
    r = await app_http.get(ME, headers={"Authorization": f"Bearer {posterior}"})
    assert r.status_code == 200, r.text


async def test_el_admin_que_se_revoca_a_si_mismo_corta_su_propio_access(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    avanzar(reloj, 1)
    r = await app_http.post(ruta(admin.id, "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    siguiente = await app_http.get(ME, headers=cabeceras(admin))
    assert siguiente.status_code == 401, siguiente.text


@pytest.mark.parametrize("objetivo", ["tecnico", "inexistente", "borrado"])
async def test_tecnico_inexistente_o_borrado_dan_404(
    objetivo: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True)
    destino = {"tecnico": SYSTEM_USER_ID, "inexistente": uuid4(), "borrado": borrado.id}[objetivo]
    r = await app_http.post(ruta(destino, "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


async def test_un_id_mal_formado_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(ruta("no-es-uuid", "revoke-sessions"), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    usuario = await usuario_real(rol)
    otro = await usuario_real("coach")
    await entrar(session, otro)
    r = await app_http.post(ruta(otro.id, "revoke-sessions"), headers=cabeceras(usuario))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await sesiones_vivas(session, otro.id, T0) == 1


async def test_sin_token_da_401(app_http: AsyncClient, usuario_real: CrearUsuario) -> None:
    otro = await usuario_real("coach")
    r = await app_http.post(ruta(otro.id, "revoke-sessions"))
    assert r.status_code == 401, r.text
