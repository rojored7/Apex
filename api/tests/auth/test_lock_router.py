"""`POST /api/v1/users/{user_id}/lock` y `/unlock` por HTTP (S2-B5; US-050; US-018; H-3).

Solo admin (coach y socio 403, sin token 401). 200 `UserOut` con `status = "locked"` o
`"active"` y `Cache-Control: no-store`. 409 `cannot_lock_self`, `already_locked` y
`not_locked`; 404 `user_not_found` para el técnico, un inexistente o una borrada; 422 con un id
mal formado. `last_admin` no se alcanza por HTTP (quien bloquea es otro admin activo); lo cubre
`test_lock_unlock.py`. Bloquear surte efecto en la siguiente petición: un access emitido antes
da 401 en `GET /auth/me` (el cargador lee la base); tras desbloquear, ese access viejo sigue
cortado por `tokens_valid_after` y uno nuevo entra.
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
from tests.auth._ciclo import ruta
from tests.auth._cuentas import CAMPOS_USER_OUT, ME, avanzar, fila_usuario
from tests.conftest import T0, Cabeceras, CrearUsuario


async def test_lock_da_200_user_out_bloqueado_sin_cache(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    r = await app_http.post(ruta(coach.id, "lock"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert set(r.json()) == CAMPOS_USER_OUT
    assert (r.json()["id"], r.json()["status"]) == (str(coach.id), "locked")
    fila = await fila_usuario(session, coach.id)
    assert fila["locked_at"] == T0 + timedelta(seconds=1)
    assert fila["tokens_valid_after"] == T0 + timedelta(seconds=1)


async def test_un_access_emitido_antes_del_bloqueo_da_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    assert (await app_http.get(ME, headers=cabeceras(coach))).status_code == 200
    avanzar(reloj, 1)
    assert (
        await app_http.post(ruta(coach.id, "lock"), headers=cabeceras(admin))
    ).status_code == 200
    r = await app_http.get(ME, headers=cabeceras(coach))
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_unlock_da_200_activo_y_solo_un_access_nuevo_entra(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    avanzar(reloj, 1)
    assert (
        await app_http.post(ruta(coach.id, "lock"), headers=cabeceras(admin))
    ).status_code == 200
    avanzar(reloj, 1)
    r = await app_http.post(ruta(coach.id, "unlock"), headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert set(r.json()) == CAMPOS_USER_OUT
    assert r.json()["status"] == "active"
    viejo = await app_http.get(ME, headers=cabeceras(coach))
    assert viejo.status_code == 401, viejo.text  # sigue cortado por tokens_valid_after
    nuevo = create_access_token(coach.id, "coach", None, reloj)
    r = await app_http.get(ME, headers={"Authorization": f"Bearer {nuevo}"})
    assert r.status_code == 200, r.text


async def test_bloquearse_a_si_mismo_da_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    await usuario_real("admin")
    r = await app_http.post(ruta(admin.id, "lock"), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "cannot_lock_self"


async def test_bloquear_una_bloqueada_da_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    bloqueado = await usuario_real("coach", bloqueado=True)
    r = await app_http.post(ruta(bloqueado.id, "lock"), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "already_locked"


async def test_desbloquear_una_no_bloqueada_da_409(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    r = await app_http.post(ruta(coach.id, "unlock"), headers=cabeceras(admin))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "not_locked"


@pytest.mark.parametrize("accion", ["lock", "unlock"])
@pytest.mark.parametrize("objetivo", ["tecnico", "inexistente", "borrado"])
async def test_tecnico_inexistente_o_borrado_dan_404(
    accion: str,
    objetivo: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    borrado = await usuario_real("coach", borrado=True, bloqueado=(accion == "unlock"))
    destino = {"tecnico": SYSTEM_USER_ID, "inexistente": uuid4(), "borrado": borrado.id}[objetivo]
    r = await app_http.post(ruta(destino, accion), headers=cabeceras(admin))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "user_not_found"


@pytest.mark.parametrize("accion", ["lock", "unlock"])
async def test_un_id_mal_formado_da_422(
    accion: str, app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(ruta("no-es-uuid", accion), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("accion", ["lock", "unlock"])
@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    accion: str,
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    usuario = await usuario_real(rol)
    otro = await usuario_real("coach", bloqueado=(accion == "unlock"))
    r = await app_http.post(ruta(otro.id, accion), headers=cabeceras(usuario))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    fila = await fila_usuario(session, otro.id)
    assert (fila["locked_at"] is not None) is (accion == "unlock")


@pytest.mark.parametrize("accion", ["lock", "unlock"])
async def test_sin_token_da_401(
    accion: str, app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    otro = await usuario_real("coach")
    r = await app_http.post(ruta(otro.id, accion))
    assert r.status_code == 401, r.text
