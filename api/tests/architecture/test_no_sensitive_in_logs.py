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

import logging

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
