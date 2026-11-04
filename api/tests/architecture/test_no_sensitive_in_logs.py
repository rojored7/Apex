"""Ningún dato sensible en claro en los logs de un flujo real (US-018 T8; S2-D20; S2-B7).

Centinela de extremo a extremo sobre la app real (`app_http`, sin lifespan): login (US-042) y
alta de socio (US-069) con los valores de `KNOWN`, más un alta repetida (409) y una inválida
(422). Se captura el stdout de los logs JSON (`capsys`, con el handler de `configure_logging`
reinstalado dentro de la captura) y los registros (`caplog`). Ninguno contiene el access token,
el refresh, la contraseña, el documento, el teléfono, el correo del socio ni un blob `apx1.`.

S3-B10 (US-074, US-075; cierra la deuda del Sprint 2): la pata de `reveal` ya corre. Login de
coach, alta, `GET /members/{id}`, `POST /members/{id}/reveal` del documento y del teléfono (el
valor en claro viaja en la respuesta) y `PATCH` del teléfono a un número nuevo: ni el stdout ni
`caplog` llevan `KNOWN_NORMALIZED`, el número nuevo (en claro o normalizado), los tokens ni un
blob `apx1.`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.logging import configure_logging
from tests.auth._sesion import LOGIN, cookie_de, post_auth
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario, SleeperEspia, UsuarioPrueba
from tests.factories.members import KNOWN, KNOWN_NORMALIZED
from tests.members._apoyo import MEMBERS, cuerpo, ruta_socio

TELEFONO_NUEVO = "+57 318 246 1357"
TELEFONO_NUEVO_NORMALIZADO = "3182461357"


async def _login(app_http: AsyncClient, usuario: UsuarioPrueba) -> tuple[str, str]:
    r = await post_auth(app_http, LOGIN, json={"email": usuario.email, "password": CLAVE_PRUEBA})
    assert r.status_code == 200, r.text
    refresh = cookie_de(r)
    assert refresh
    return r.json()["access_token"], refresh


async def test_login_y_alta_de_socio_no_dejan_datos_en_los_logs(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    sleeper_nulo: SleeperEspia,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging(api_prueba.state.settings)  # el handler escribe en el stdout de capsys
    caplog.set_level(logging.DEBUG)
    coach = await usuario_real("coach")
    access, refresh = await _login(app_http, coach)
    con_access = {**cabeceras(coach), "Authorization": f"Bearer {access}"}

    creado = await app_http.post(MEMBERS, json=cuerpo(), headers=con_access)
    assert creado.status_code == 201, creado.text
    repetido = await app_http.post(MEMBERS, json=cuerpo(), headers=con_access)
    assert repetido.status_code == 409, repetido.text
    invalido = await app_http.post(MEMBERS, json=cuerpo(phone="+57"), headers=con_access)
    assert invalido.status_code == 422, invalido.text

    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    prohibidos = (access, refresh, coach.token, CLAVE_PRUEBA, "apx1.", *KNOWN_NORMALIZED)
    for valor in prohibidos:
        assert valor not in texto, valor[:12]


async def test_reveal_no_deja_el_valor_revelado_en_los_logs(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    sleeper_nulo: SleeperEspia,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging(api_prueba.state.settings)
    caplog.set_level(logging.DEBUG)
    coach = await usuario_real("coach")
    access, refresh = await _login(app_http, coach)
    con_access = {**cabeceras(coach), "Authorization": f"Bearer {access}"}

    creado = await app_http.post(MEMBERS, json=cuerpo(), headers=con_access)
    assert creado.status_code == 201, creado.text
    ruta = ruta_socio(creado.json()["id"])
    ficha = await app_http.get(ruta, headers=con_access)
    assert ficha.status_code == 200, ficha.text
    for campo in ("document", "phone"):
        revelado = await app_http.post(f"{ruta}/reveal", json={"field": campo}, headers=con_access)
        assert revelado.status_code == 200, revelado.text
        assert revelado.json() == {"field": campo, "value": KNOWN[campo]}
    editado = await app_http.patch(ruta, json={"phone": TELEFONO_NUEVO}, headers=con_access)
    assert editado.status_code == 200, editado.text

    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    prohibidos = (
        access,
        refresh,
        coach.token,
        CLAVE_PRUEBA,
        "apx1.",
        TELEFONO_NUEVO,
        TELEFONO_NUEVO_NORMALIZADO,
        *KNOWN_NORMALIZED,
    )
    for valor in prohibidos:
        assert valor not in texto, valor[:12]


# S5-W0-3 (S5-D58, M-8): ni el token del bot ni el de OpenBao salen en los logs ------------------

TOKEN_BOT = "bot123456:AAH" + "z" * 30
URL_BOT = f"https://api.telegram.org/{TOKEN_BOT}/sendMessage"
TOKEN_BAO = "hvs.CAESI" + "q" * 24


def _salida_de_un_registro(
    capsys: pytest.CaptureFixture[str], emitir: Callable[[logging.Logger], None]
) -> str:
    """Instala el handler JSON de `configure_logging` dentro de la captura y emite un registro."""
    configure_logging(SimpleNamespace(LOG_LEVEL="DEBUG"))  # type: ignore[arg-type]
    emitir(logging.getLogger("app.alerts"))
    salida = capsys.readouterr()
    return salida.out + salida.err


def test_un_error_de_httpx_con_la_url_del_bot_no_deja_el_token_en_el_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def emitir(logger: logging.Logger) -> None:
        try:
            raise httpx.ConnectError(f"All connection attempts failed: {URL_BOT}")
        except httpx.ConnectError:
            logger.exception("falló el envío a Telegram: %s", URL_BOT)

    texto = _salida_de_un_registro(capsys, emitir)
    assert "falló el envío" in texto, "no se capturó el registro"
    assert "AAH" not in texto and "123456" not in texto


def test_httpx_a_info_contra_un_transporte_falso_no_escribe_la_url_del_bot(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`configure_logging` fija `httpx` y `httpcore` en WARNING: la URL (con el token) no se
    escribe aunque la raíz esté en DEBUG."""

    async def llamar() -> None:
        transporte = httpx.MockTransport(lambda _peticion: httpx.Response(200, json={"ok": True}))
        async with httpx.AsyncClient(transport=transporte) as cliente:
            await cliente.post(URL_BOT, json={"chat_id": "1", "text": "hola"})

    def emitir(logger: logging.Logger) -> None:
        asyncio.run(llamar())
        logger.info("pasó por httpx")

    texto = _salida_de_un_registro(capsys, emitir)
    assert "pasó por httpx" in texto
    assert "AAH" not in texto and "api.telegram.org/bot" not in texto


def test_la_cabecera_x_vault_token_en_un_extra_no_llega_al_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def emitir(logger: logging.Logger) -> None:
        logger.warning(
            "peticion a openbao",
            extra={"headers": {"X-Vault-Token": TOKEN_BAO}, "smtp_password": "clave-smtp-x"},
        )

    texto = _salida_de_un_registro(capsys, emitir)
    assert "peticion a openbao" in texto
    assert TOKEN_BAO not in texto and "clave-smtp-x" not in texto


def test_el_token_de_openbao_en_el_texto_de_un_error_no_llega_al_log_por_clave_conocida(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """El proveedor nunca copia el cuerpo ni el token (S5-D17); y si un `extra` los trae con la
    clave `telegram_bot_token` o `bot_token` tampoco se escriben."""

    def emitir(logger: logging.Logger) -> None:
        logger.error(
            "alerta no enviada", extra={"telegram_bot_token": TOKEN_BOT, "bot_token": "x" * 30}
        )

    texto = _salida_de_un_registro(capsys, emitir)
    assert "alerta no enviada" in texto
    assert TOKEN_BOT not in texto and "x" * 30 not in texto
