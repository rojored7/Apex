"""Ningún dato sensible en claro en los logs de un flujo real (US-018 T8; S2-D20; S2-B7).

Centinela de extremo a extremo sobre la app real (`app_http`, sin lifespan): login (US-042) y
alta de socio (US-069) con los valores de `KNOWN`, más un alta repetida (409) y una inválida
(422). Se captura el stdout de los logs JSON (`capsys`, con el handler de `configure_logging`
reinstalado dentro de la captura) y los registros (`caplog`). Ninguno contiene el access token,
el refresh, la contraseña, el documento, el teléfono, el correo del socio ni un blob `apx1.`.

La pata de `reveal` (US-074) queda como prueba aparte, saltada con dueño S3-B10.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.logging import configure_logging
from tests.auth._sesion import LOGIN, cookie_de, post_auth
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario, SleeperEspia, UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED
from tests.members._apoyo import MEMBERS, cuerpo


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


@pytest.mark.skip(reason="US-074, S3-B10")
async def test_reveal_no_deja_el_valor_revelado_en_los_logs() -> None:
    raise AssertionError("S3-B10: revelar un campo y buscar el claro en stdout y caplog")
