"""Auditoría del login por HTTP (S2-B6; US-107; S2-D43, L-8, N-31).

`POST /api/v1/auth/login` emite `LoginAttempted` y el módulo `audit` lo registra en la misma
transacción. El 401 de un correo existente confirma antes de lanzar (S2-D8): la fila sobrevive
al rollback de `get_session`. La fila guarda la IP del cliente y su `User-Agent`, nunca el correo
tecleado. Cliente `cliente_desde(IP_A)` sobre la sesión de la prueba; piso de login anulado.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth._cuentas import filas_auditoria
from tests.auth._sesion import IP_A, LOGIN, post_auth
from tests.conftest import CLAVE_PRUEBA, ClienteDesde, CrearUsuario

ERRADA = "Otra-Clave-Distinta-77"
UA = "navegador-de-prueba/2.0"


def _cuerpo(email: str, password: str = CLAVE_PRUEBA) -> dict[str, str]:
    return {"email": email, "password": password}


async def _filas_login(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    filas = await filas_auditoria(session, "auth.users", user_id)
    return [f for f in filas if f["action"] == "login"]


def _cliente(cliente_desde: ClienteDesde) -> AsyncClient:
    return cliente_desde(IP_A)


async def test_login_correcto_por_http_deja_su_fila_con_ip_y_user_agent(
    session: AsyncSession, usuario_real: CrearUsuario, cliente_desde: ClienteDesde
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(
        _cliente(cliente_desde), LOGIN, json=_cuerpo(coach.email), headers={"User-Agent": UA}
    )
    assert r.status_code == 200, r.text
    (fila,) = await _filas_login(session, coach.id)
    assert fila["user_id"] == coach.id and fila["record_id"] == coach.id
    assert fila["after"]["result"] == "ok"
    assert fila["after"]["ip"] == IP_A
    assert fila["after"]["user_agent"] == UA


async def test_login_fallido_por_http_deja_su_fila_que_sobrevive_al_401(
    session: AsyncSession, usuario_real: CrearUsuario, cliente_desde: ClienteDesde
) -> None:
    coach = await usuario_real("coach")
    r = await post_auth(
        _cliente(cliente_desde),
        LOGIN,
        json=_cuerpo(coach.email, ERRADA),
        headers={"User-Agent": UA},
    )
    assert r.status_code == 401
    (fila,) = await _filas_login(session, coach.id)
    assert fila["after"]["result"] == "failed"
    assert fila["after"]["reason"] == "bad_password"
    assert fila["after"]["ip"] == IP_A
    assert fila["after"]["user_agent"] == UA


async def test_la_fila_de_login_no_lleva_el_correo_tecleado_ni_la_contrasena(
    session: AsyncSession, usuario_real: CrearUsuario, cliente_desde: ClienteDesde
) -> None:
    coach = await usuario_real("coach")
    tecleado = f" {coach.email.upper()} "
    cliente = _cliente(cliente_desde)
    assert (await post_auth(cliente, LOGIN, json=_cuerpo(tecleado))).status_code == 200
    assert (await post_auth(cliente, LOGIN, json=_cuerpo(tecleado, ERRADA))).status_code == 401
    filas = await _filas_login(session, coach.id)
    assert [f["after"]["result"] for f in filas] == ["ok", "failed"]
    volcado = json.dumps([[f["before"], f["after"]] for f in filas], ensure_ascii=False).lower()
    for prohibido in (coach.email, coach.email.split("@")[0], CLAVE_PRUEBA, ERRADA):
        assert prohibido.lower() not in volcado


async def test_cinco_fallidos_por_http_dejan_cinco_filas_y_el_sexto_429_ninguna(
    session: AsyncSession, usuario_real: CrearUsuario, cliente_desde: ClienteDesde
) -> None:
    """`LOGIN_IP_LIMIT=5` (E5): el sexto se corta por IP antes del service; la auditoría no
    cuenta intentos."""
    coach = await usuario_real("coach")
    cliente = _cliente(cliente_desde)
    for _ in range(5):
        r = await post_auth(cliente, LOGIN, json=_cuerpo(coach.email, ERRADA))
        assert r.status_code == 401
    sexto = await post_auth(cliente, LOGIN, json=_cuerpo(coach.email, ERRADA))
    assert sexto.status_code == 429
    filas = await _filas_login(session, coach.id)
    assert len(filas) == 5
    assert {f["after"]["result"] for f in filas} == {"failed"}
