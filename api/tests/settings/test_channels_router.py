"""`GET` y `PATCH /settings/channels` con el api real (US-122; S5-D30, E10). Rojo B4.

E10: el router de secciones es genérico (`/settings/{section}`); no se añaden rutas tipadas.
Solo admin (coach y socio 403, sin token 401), versión vieja 409, valor inválido 422 con `field`,
cubeta `admin-write` (429). El `GET` suma `credentials_present {email, telegram}`, calculado desde
`Settings` del proceso (`app.state.settings`), sin ningún valor secreto; la auditoría tampoco.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.core._canales_apoyo import CHAT_ID, TOKEN_BOT
from tests.settings._apoyo import API, CHANNELS_OK, fila, filas_de_auditoria

RUTA = f"{API}/settings/channels"
CLAVE_SMTP = "clave-smtp-no-real"


@pytest.fixture
async def admin(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _patch(
    cliente: AsyncClient, cabeceras: dict[str, str], valor: dict[str, Any], version: int
) -> Response:
    return await cliente.patch(RUTA, headers=cabeceras, json={"value": valor, "version": version})


def _con_credenciales(api: FastAPI) -> None:
    api.state.settings = api.state.settings.model_copy(
        update={
            "SMTP_HOST": "smtp.ejemplo.test",
            "SMTP_USER": "apex",
            "SMTP_PASSWORD": CLAVE_SMTP,
            "SMTP_FROM": "apex@ejemplo.test",
            "TELEGRAM_BOT_TOKEN": TOKEN_BOT,
            "TELEGRAM_CHAT_ID": CHAT_ID,
        }
    )


async def test_admin_lee_los_defaults_en_version_0_y_sin_credenciales(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await app_http.get(RUTA, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["key"], cuerpo["version"]) == ("channels", 0)
    assert (cuerpo["updated_at"], cuerpo["updated_by"]) == (None, None)
    assert cuerpo["value"]["email"]["enabled"] is False
    assert cuerpo["value"]["whatsapp"] == {"enabled": False, "country_code": "57"}
    assert cuerpo["value"]["telegram"] == {"enabled": False}
    assert cuerpo["credentials_present"] == {"email": False, "telegram": False}
    assert "no-store" in r.headers["cache-control"]


async def test_el_get_refleja_las_credenciales_de_settings_sin_exponer_ningun_valor(
    app_http: AsyncClient, api_prueba: FastAPI, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    _con_credenciales(api_prueba)

    r = await app_http.get(RUTA, headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert r.json()["credentials_present"] == {"email": True, "telegram": True}
    for secreto in (CLAVE_SMTP, TOKEN_BOT, CHAT_ID, "smtp.ejemplo.test", "apex@ejemplo.test"):
        assert secreto not in r.text


async def test_activar_el_correo_sin_credenciales_se_permite(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)

    assert r.status_code == 200, r.text
    leido = (await app_http.get(RUTA, headers=cabeceras(admin))).json()
    assert leido["value"]["email"]["enabled"] is True
    assert leido["credentials_present"] == {"email": False, "telegram": False}


async def test_admin_guarda_y_lee_lo_guardado(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["key"], cuerpo["version"], cuerpo["value"]) == ("channels", 1, CHANNELS_OK)
    assert cuerpo["updated_by"] == str(admin.id)
    leido = (await app_http.get(RUTA, headers=cabeceras(admin))).json()
    assert (leido["version"], leido["value"]) == (1, CHANNELS_OK)


async def test_la_auditoria_del_guardado_no_lleva_secretos_de_settings(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    _con_credenciales(api_prueba)

    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)

    assert r.status_code == 200, r.text
    auditoria = await filas_de_auditoria(session)
    assert [f["action"] for f in auditoria] == ["insert"]
    assert auditoria[0]["after"]["value"] == CHANNELS_OK
    texto = json.dumps(auditoria, default=str)
    for secreto in (CLAVE_SMTP, TOKEN_BOT, CHAT_ID, "credentials_present"):
        assert secreto not in texto


@pytest.mark.parametrize("metodo", ["GET", "PATCH"])
async def test_coach_403_en_get_y_patch_sin_escribir(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    metodo: str,
) -> None:
    coach = await usuario_real("coach")
    cuerpo = {"value": CHANNELS_OK, "version": 0} if metodo == "PATCH" else None

    r = await app_http.request(metodo, RUTA, headers=cabeceras(coach), json=cuerpo)

    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert await fila(session, "channels") is None


async def test_socio_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")

    assert (await app_http.get(RUTA, headers=cabeceras(socio))).status_code == 403
    sin_token = await app_http.get(RUTA)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


async def test_version_vieja_da_409_sin_tocar_la_fila(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    assert (await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)).status_code == 200

    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)

    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"
    guardada = await fila(session, "channels")
    assert guardada is not None and guardada["version"] == 1


@pytest.mark.parametrize(
    ("ruta", "valor", "campo"),
    [
        (("email", "smtp_password"), "x", "value.email.smtp_password"),
        (("telegram", "token"), "123456:AAH-no-debe-salir", "value.telegram.token"),
        (("telegram", "chat_id"), "-100", "value.telegram.chat_id"),
        (("email", "sender_name"), "Ana\r\nBcc: espia@malo.test", "value.email.sender_name"),
        (("email", "reply_to"), "no-es-correo", "value.email.reply_to"),
        (("whatsapp", "country_code"), "abc", "value.whatsapp.country_code"),
    ],
    ids=["smtp_password", "token", "chat_id", "crlf", "reply_to", "country_code"],
)
async def test_un_valor_invalido_o_un_secreto_da_422_con_field_sin_crear_fila(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    ruta: tuple[str, str],
    valor: str,
    campo: str,
) -> None:
    cuerpo = copy.deepcopy(CHANNELS_OK)
    cuerpo[ruta[0]][ruta[1]] = valor

    r = await _patch(app_http, cabeceras(admin), cuerpo, 0)

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert "AAH-no-debe-salir" not in r.text
    assert await fila(session, "channels") is None


async def test_una_clave_ajena_en_la_raiz_da_422(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _patch(app_http, cabeceras(admin), {**CHANNELS_OK, "sms": {"enabled": True}}, 0)

    assert r.status_code == 422
    assert r.json()["error"]["field"] == "value.sms"


async def test_el_router_es_el_generico_no_hay_ruta_tipada_de_channels(
    api_prueba: FastAPI,
) -> None:
    """E10: `GET|PATCH /settings/channels` los atiende `/settings/{section}`."""
    rutas = api_prueba.openapi()["paths"]

    assert f"{API}/settings/channels" not in rutas
    assert {"get", "patch"} <= set(rutas[f"{API}/settings/{{section}}"])


async def test_patch_de_channels_consume_admin_write_y_el_31_da_429(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    primero = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)
    assert primero.status_code == 200, primero.text
    for _ in range(29):
        r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)
        assert r.status_code == 409, r.text

    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 1)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    session.expire_all()
    guardada = await fila(session, "channels")
    assert guardada is not None and guardada["version"] == 1


async def test_el_patch_devuelve_credentials_present_igual_que_el_get(
    app_http: AsyncClient, api_prueba: FastAPI, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    """Revisión de seguridad (LOW 8): misma forma de respuesta en `GET` y `PATCH`."""
    _con_credenciales(api_prueba)

    r = await _patch(app_http, cabeceras(admin), CHANNELS_OK, 0)

    assert r.status_code == 200, r.text
    assert r.json()["credentials_present"] == {"email": True, "telegram": True}
    for secreto in (CLAVE_SMTP, TOKEN_BOT, CHAT_ID, "smtp.ejemplo.test", "apex@ejemplo.test"):
        assert secreto not in r.text
