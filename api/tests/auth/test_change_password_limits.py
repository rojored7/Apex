"""Límites de `POST /api/v1/auth/me/password` (S2-B3, revisión de seguridad: HIGH-1).

Cada intento cuesta hasta tres argon2 y un access robado no debe poder adivinar la contraseña
actual sin tope:
- por usuario: 5 fallos de la contraseña actual en 900 s y el siguiente intento da 429
  `rate_limited` antes de argon2, aunque traiga la contraseña correcta; un éxito no suma;
- por IP: 10 peticiones por minuto (`rate_limit("change-password")`), sea cual sea el usuario.
`reset_store` (autouse) limpia los contadores entre pruebas.
"""

from __future__ import annotations

from httpx import AsyncClient, Response

from app.modules.auth.router import CHANGE_PASSWORD_IP_LIMIT
from app.modules.auth.service import CHANGE_PASSWORD_USER_LIMIT
from tests.auth._cuentas import NUEVA, PASSWORD
from tests.auth._sesion import post_auth
from tests.conftest import CLAVE_PRUEBA, CrearUsuario, UsuarioPrueba

ERRADA = "No-Es-La-Actual-1"


async def _intento(cliente: AsyncClient, usuario: UsuarioPrueba, actual: str) -> Response:
    return await post_auth(
        cliente,
        PASSWORD,
        json={"current_password": actual, "new_password": NUEVA},
        headers={"Authorization": f"Bearer {usuario.token}"},
    )


async def test_tras_cinco_fallos_el_usuario_recibe_429_aunque_acierte(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    assert CHANGE_PASSWORD_USER_LIMIT == 5
    coach = await usuario_real("coach")
    for _ in range(CHANGE_PASSWORD_USER_LIMIT):
        r = await _intento(app_http, coach, ERRADA)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_current_password"
    bloqueado = await _intento(app_http, coach, CLAVE_PRUEBA)
    assert bloqueado.status_code == 429, bloqueado.text
    assert bloqueado.json()["error"]["code"] == "rate_limited"
    assert int(bloqueado.headers["retry-after"]) >= 1


async def test_el_limite_por_usuario_no_afecta_a_otro_usuario(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    primero = await usuario_real("coach")
    for _ in range(CHANGE_PASSWORD_USER_LIMIT):
        await _intento(app_http, primero, ERRADA)
    otro = await usuario_real("coach")
    assert (await _intento(app_http, otro, CLAVE_PRUEBA)).status_code == 200


async def test_por_ip_la_peticion_once_del_minuto_da_429(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    assert CHANGE_PASSWORD_IP_LIMIT == 10
    usuarios = [await usuario_real("coach") for _ in range(3)]
    for i in range(CHANGE_PASSWORD_IP_LIMIT):
        r = await _intento(app_http, usuarios[i // 4], ERRADA)
        assert r.status_code == 422, (i, r.text)
    r = await _intento(app_http, usuarios[2], ERRADA)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
