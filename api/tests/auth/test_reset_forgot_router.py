"""`POST /api/v1/auth/forgot` y `POST /api/v1/auth/reset` por HTTP (S2-B4; US-048; H-2 / S2-D36,
L-12, S2-D47).

Ambas son públicas (sin `Authorization`), no usan la cookie y por eso no exigen `Origin`
(S2-D38 solo aplica a login, refresh y logout). `forgot` responde siempre 204 con el cuerpo
vacío, exista o no la cuenta; `reset` responde 204 sin cuerpo y sin `Set-Cookie` (no inicia
sesión). Límites por IP desde `app.state.rate_limits` (E5): `FORGOT_IP_LIMIT = 5` y
`RESET_IP_LIMIT = 10` por 60 s; el intento siguiente da 429 con `Retry-After`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security import verify_password
from tests.auth._cuentas import NUEVA, fila_usuario, tokens_de
from tests.conftest import ClienteDesde, CrearUsuario
from tests.factories.users import make_one_time_token

FORGOT = "/api/v1/auth/forgot"
RESET = "/api/v1/auth/reset"
MENSAJE_INVALIDO = "El enlace ya no es válido. Pide uno nuevo al administrador."


def _sin_fecha(respuesta: Response) -> dict[str, str]:
    # `date` y `x-request-id` cambian en cada petición; todo lo demás debe ser idéntico.
    return {k: v for k, v in respuesta.headers.items() if k.lower() not in {"date", "x-request-id"}}


# forgot ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [{}, {"bloqueado": True}, {"password": None}, {"borrado": True}],
    ids=["activo", "bloqueado", "pendiente", "borrado"],
)
async def test_forgot_responde_204_sin_cuerpo_para_toda_cuenta(
    cambios: dict[str, Any], app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    usuario = await usuario_real("coach", **cambios)
    r = await app_http.post(FORGOT, json={"email": usuario.email})
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert "set-cookie" not in r.headers


async def test_forgot_existente_e_inexistente_son_indistinguibles(
    app_http: AsyncClient, usuario_real: CrearUsuario
) -> None:
    coach = await usuario_real("coach")
    existe = await app_http.post(FORGOT, json={"email": coach.email})
    no_existe = await app_http.post(FORGOT, json={"email": "nadie-router@test.apex"})
    assert (existe.status_code, existe.content) == (no_existe.status_code, no_existe.content)
    assert existe.status_code == 204
    assert _sin_fecha(existe) == _sin_fecha(no_existe)


async def test_forgot_no_crea_tokens(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(FORGOT, json={"email": coach.email})
    assert r.status_code == 204
    assert await tokens_de(session, coach.id) == []


async def test_forgot_funciona_sin_authorization_ni_origin(app_http: AsyncClient) -> None:
    r = await app_http.post(FORGOT, json={"email": "sin-cabeceras@test.apex"})
    assert r.status_code == 204, r.text


async def test_forgot_el_sexto_por_ip_da_429(app_http: AsyncClient) -> None:
    for i in range(5):
        r = await app_http.post(FORGOT, json={"email": f"ip-{i}@test.apex"})
        assert r.status_code == 204, (i, r.text)
    r = await app_http.post(FORGOT, json={"email": "ip-6@test.apex"})
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


async def test_forgot_el_sexto_por_cuenta_da_429_desde_otra_ip(
    cliente_desde: ClienteDesde,
) -> None:
    """S2-D36: el límite por cuenta no depende de la IP."""
    correo = "cuenta-router@test.apex"
    for i in range(5):
        r = await cliente_desde(f"198.51.{i}.7").post(FORGOT, json={"email": correo})
        assert r.status_code == 204, (i, r.text)
    r = await cliente_desde("192.0.2.200").post(FORGOT, json={"email": correo.upper()})
    assert r.status_code == 429, r.text


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"email": "a" * 243 + "@test.apex.co"}, "email"),
        ({"email": "sin-arroba"}, "email"),
        ({}, "email"),
        ({"email": "x@test.apex", "extra": 1}, "extra"),
    ],
    ids=["mas-de-254", "sin-arroba", "sin-correo", "campo-de-mas"],
)
async def test_forgot_cuerpo_invalido_da_422_con_el_campo(
    cuerpo: dict[str, Any], campo: str, app_http: AsyncClient
) -> None:
    r = await app_http.post(FORGOT, json=cuerpo)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo


async def test_forgot_acepta_un_correo_de_254(app_http: AsyncClient) -> None:
    correo = "a" * 241 + "@test.apex.co"
    assert len(correo) == 254
    r = await app_http.post(FORGOT, json={"email": correo})
    assert r.status_code == 204, r.text


# reset -----------------------------------------------------------------------------------


async def test_reset_valido_da_204_sin_cuerpo_ni_cookie(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    pendiente = await usuario_real("coach", password=None)
    claro, _ = await make_one_time_token(
        session, pendiente, "activate", expires_in=timedelta(hours=72)
    )
    r = await app_http.post(RESET, json={"token": claro, "new_password": NUEVA})
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert "set-cookie" not in r.headers
    datos = await fila_usuario(session, pendiente.id)
    assert verify_password(datos["password_hash"], NUEVA) is True


async def test_reset_con_token_invalido_da_400_invalid_token(app_http: AsyncClient) -> None:
    r = await app_http.post(RESET, json={"token": "x" * 43, "new_password": NUEVA})
    assert r.status_code == 400, r.text
    error = r.json()["error"]
    assert (error["code"], error["message"]) == ("invalid_token", MENSAJE_INVALIDO)
    assert error.get("field") is None


async def test_reset_con_contrasena_debil_da_422_y_no_gasta_el_token(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    session: AsyncSession,
    reloj: FrozenClock,
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    r = await app_http.post(RESET, json={"token": claro, "new_password": "corta"})
    assert r.status_code == 422, r.text  # M5: `minLength: 12` del contrato
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == (
        "validation_error",
        "new_password",
    )
    r = await app_http.post(RESET, json={"token": claro, "new_password": "Cambiar-Esto"})
    assert r.status_code == 422, r.text  # la política sigue: una común
    assert (r.json()["error"]["code"], r.json()["error"]["field"]) == (
        "weak_password",
        "new_password",
    )
    (fila,) = await tokens_de(session, coach.id)
    assert fila.used_at is None


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"token": "x" * 19, "new_password": NUEVA}, "token"),
        ({"token": "x" * 201, "new_password": NUEVA}, "token"),
        ({"token": "x" * 43, "new_password": "y" * 129}, "new_password"),
        ({"token": "x" * 43}, "new_password"),
        ({"new_password": NUEVA}, "token"),
        ({"token": "x" * 43, "new_password": NUEVA, "email": "a@test.apex"}, "email"),
    ],
    ids=["token-19", "token-201", "clave-129", "sin-clave", "sin-token", "campo-de-mas"],
)
async def test_reset_cuerpo_invalido_da_422_con_el_campo(
    cuerpo: dict[str, Any], campo: str, app_http: AsyncClient
) -> None:
    r = await app_http.post(RESET, json=cuerpo)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["field"] == campo


async def test_reset_funciona_sin_authorization_ni_origin(
    app_http: AsyncClient, usuario_real: CrearUsuario, session: AsyncSession, reloj: FrozenClock
) -> None:
    coach = await usuario_real("coach")
    claro, _ = await make_one_time_token(session, coach, "reset", expires_in=timedelta(hours=1))
    r = await app_http.post(RESET, json={"token": claro, "new_password": NUEVA}, headers={})
    assert r.status_code == 204, r.text


async def test_reset_por_encima_del_tope_por_ip_da_429(
    app_http: AsyncClient, api_prueba: FastAPI
) -> None:
    """L-12 y E5: `RESET_IP_LIMIT = 10` por 60 s; el undécimo da 429."""
    limite, ventana = api_prueba.state.rate_limits["reset"]
    assert (limite, ventana) == (10, 60)
    for i in range(limite):
        r = await app_http.post(RESET, json={"token": f"{i:0>43}", "new_password": NUEVA})
        assert r.status_code == 400, (i, r.text)
    r = await app_http.post(RESET, json={"token": "z" * 43, "new_password": NUEVA})
    assert r.status_code == 429, r.text
    assert int(r.headers["retry-after"]) >= 1
