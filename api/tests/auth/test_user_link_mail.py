"""Correo del alta y del reenvío: `email_sent` (S5-B9, US-131; S5-D37, S5-D205, M-7d). # Rojo B9

`create_user` y `resend_link` envían de forma síncrona (`await send_mail`) y devuelven
`email_sent: bool`: `true` solo con SMTP configurado Y `channels.email.enabled`; cualquier otra
combinación da `false` y nada sale. El correo lleva el asunto y el cuerpo de `mail_texts` con el
enlace completo y el nombre de `channels.email.sender_name`. Un fallo del correo (de SMTP o una
excepción cualquiera) no cambia el 201/200 y deja `email_sent = false`; el enlace nunca llega a
los logs. Contrato de firma que fija el Rojo: `settings=` por palabra clave en el service.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.modules.auth import mail_texts, service
from app.modules.auth.schemas import CreateUserOut, IssuedLinkOut
from tests.auth._correos import (
    NOMBRE_REMITENTE,
    EntornoCorreo,
    entorno_correo,
    habilitar_canal_correo,
    hacer_que_send_mail_lance,
    token_del_cuerpo,
)
from tests.auth._cuentas import tokens_de
from tests.conftest import Cabeceras, CrearUsuario

FRONT = "https://gym.ejemplo.test"
USERS = "/api/v1/users"
CASOS = [
    (True, True, True),
    (True, False, False),
    (False, True, False),
    (False, False, False),
]
IDS_CASOS = ["smtp-y-canal", "smtp-sin-canal", "canal-sin-smtp", "nada"]


async def _crear(session: AsyncSession, **kw: Any) -> CreateUserOut:
    with actor_scope(kw["by"]):
        return await service.create_user(session, **kw)


async def _reenviar(session: AsyncSession, user_id: UUID, **kw: Any) -> IssuedLinkOut:
    with actor_scope(kw["by"]):
        return await service.resend_link(session, user_id, **kw)


def _cuerpo(mensaje: EmailMessage) -> str:
    contenido = mensaje.get_content()
    assert isinstance(contenido, str)
    return contenido


async def _preparar(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    admin_id: object,
    *,
    smtp: bool,
    canal: bool,
) -> EntornoCorreo:
    entorno = entorno_correo(monkeypatch, api_prueba, session, con_smtp_=smtp)
    if canal:
        await habilitar_canal_correo(session, admin_id)  # type: ignore[arg-type]
    return entorno


@pytest.mark.parametrize(("smtp", "canal", "esperado"), CASOS, ids=IDS_CASOS)
async def test_el_alta_marca_email_sent_solo_con_smtp_y_canal(
    smtp: bool,
    canal: bool,
    esperado: bool,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=smtp, canal=canal)

    salida = await _crear(
        session,
        email="alta-correo@test.apex",
        role="coach",
        by=admin.id,
        front_base_url=FRONT,
        settings=entorno.settings,
    )

    assert salida.email_sent is esperado
    assert len(entorno.smtp.mensajes) == (1 if esperado else 0)
    assert salida.activation_url.startswith(f"{FRONT}/restablecer/")


@pytest.mark.parametrize(("smtp", "canal", "esperado"), CASOS, ids=IDS_CASOS)
async def test_el_reenvio_marca_email_sent_solo_con_smtp_y_canal(
    smtp: bool,
    canal: bool,
    esperado: bool,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=smtp, canal=canal)

    salida = await _reenviar(
        session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
    )

    assert salida.email_sent is esperado
    assert len(entorno.smtp.mensajes) == (1 if esperado else 0)


async def test_el_correo_del_alta_lleva_el_texto_fijo_de_activacion(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    salida = await _crear(
        session,
        email="Destino.Alta@Test.Apex",
        role="coach",
        by=admin.id,
        front_base_url=FRONT,
        settings=entorno.settings,
    )

    (mensaje,) = entorno.smtp.mensajes
    asunto, cuerpo = mail_texts.activation_mail(salida.activation_url, NOMBRE_REMITENTE)
    assert mensaje["To"] == "destino.alta@test.apex"
    assert mensaje["Subject"] == asunto
    assert _cuerpo(mensaje).strip() == cuerpo.strip()
    assert NOMBRE_REMITENTE in mensaje["From"]
    assert salida.activation_url in _cuerpo(mensaje)


async def test_el_reenvio_a_una_cuenta_pendiente_usa_el_texto_de_activacion(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    salida = await _reenviar(
        session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
    )

    (mensaje,) = entorno.smtp.mensajes
    asunto, cuerpo = mail_texts.activation_mail(salida.url, NOMBRE_REMITENTE)
    assert salida.purpose == "activate"
    assert mensaje["To"] == pendiente.email
    assert (mensaje["Subject"], _cuerpo(mensaje).strip()) == (asunto, cuerpo.strip())


async def test_el_reenvio_a_una_cuenta_activa_usa_el_texto_de_recuperacion(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    salida = await _reenviar(
        session, coach.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
    )

    (mensaje,) = entorno.smtp.mensajes
    asunto, cuerpo = mail_texts.reset_mail(salida.url, NOMBRE_REMITENTE)
    assert salida.purpose == "reset"
    assert (mensaje["Subject"], _cuerpo(mensaje).strip()) == (asunto, cuerpo.strip())


async def test_un_fallo_de_smtp_deja_la_cuenta_creada_y_email_sent_falso(
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)
    entorno.smtp.fallo = smtplib.SMTPRecipientsRefused({})

    salida = await _crear(
        session,
        email="rechazado@test.apex",
        role="coach",
        by=admin.id,
        front_base_url=FRONT,
        settings=entorno.settings,
    )

    assert entorno.smtp.conexiones, "debió intentar enviar"
    assert salida.email_sent is False
    assert salida.user.email == "rechazado@test.apex"
    assert salida.activation_url.startswith(f"{FRONT}/restablecer/")


@pytest.mark.parametrize("operacion", ["alta", "reenvio"])
async def test_una_excepcion_del_correo_no_cambia_la_respuesta_ni_filtra_el_enlace(
    operacion: str,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """M-7d: se captura TODA excepción del correo y solo se registra su tipo."""
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)
    cuerpos = hacer_que_send_mail_lance(monkeypatch)
    caplog.set_level(logging.DEBUG)

    if operacion == "alta":
        salida = await _crear(
            session,
            email="lanza@test.apex",
            role="coach",
            by=admin.id,
            front_base_url=FRONT,
            settings=entorno.settings,
        )
        enlace = salida.activation_url
    else:
        salida = await _reenviar(
            session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
        )
        enlace = salida.url

    assert salida.email_sent is False
    assert len(cuerpos) == 1, "send_mail debió llamarse una vez"
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert enlace not in texto
    assert token_del_cuerpo(enlace) not in texto
    assert "RuntimeError" in texto, "el log debe llevar el tipo de la excepción"


@pytest.mark.parametrize("operacion", ["alta", "reenvio"])
async def test_el_enlace_enviado_nunca_aparece_en_los_logs(
    operacion: str,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)
    caplog.set_level(logging.DEBUG)

    if operacion == "alta":
        salida = await _crear(
            session,
            email="log-alta@test.apex",
            role="coach",
            by=admin.id,
            front_base_url=FRONT,
            settings=entorno.settings,
        )
    else:
        salida = await _reenviar(
            session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
        )

    assert salida.email_sent is True
    (mensaje,) = entorno.smtp.mensajes
    token = token_del_cuerpo(_cuerpo(mensaje))
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert token not in texto
    assert "log-alta@test.apex" not in texto


async def test_post_users_con_smtp_y_canal_responde_201_con_email_sent_true(
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    r = await app_http.post(
        USERS, json={"email": "http-alta@test.apex", "role": "coach"}, headers=cabeceras(admin)
    )

    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is True
    (mensaje,) = entorno.smtp.mensajes
    assert r.json()["activation_url"] in _cuerpo(mensaje)


async def test_post_users_sin_smtp_responde_201_con_email_sent_false(
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=False, canal=True)

    r = await app_http.post(
        USERS, json={"email": "http-sin@test.apex", "role": "coach"}, headers=cabeceras(admin)
    )

    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is False
    assert entorno.smtp.mensajes == []


async def test_el_reenvio_http_con_smtp_y_canal_envia_y_responde_email_sent_true(
    monkeypatch: pytest.MonkeyPatch,
    app_http: AsyncClient,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    r = await app_http.post(f"{USERS}/{pendiente.id}/resend-link", headers=cabeceras(admin))

    assert r.status_code == 200, r.text
    assert r.json()["email_sent"] is True
    (mensaje,) = entorno.smtp.mensajes
    assert mensaje["To"] == pendiente.email
    assert r.json()["url"] in _cuerpo(mensaje)


# S5-D238 / S5-D239 (revisión de seguridad de B9) ---------------------------------------


def _hacer_que_send_mail_se_cuelgue(monkeypatch: pytest.MonkeyPatch) -> None:
    """`send_mail` espera un `asyncio.Event` que nunca se activa (sin `sleep` real)."""
    nunca = asyncio.Event()

    async def colgado(*args: Any, **kwargs: Any) -> None:
        await nunca.wait()

    for modulo in ("app.modules.auth.links", "app.modules.auth.users"):
        monkeypatch.setattr(f"{modulo}.send_mail", colgado)
    monkeypatch.setattr("app.modules.auth.links.AUTH_MAIL_TIMEOUT_S", 0.05)


@pytest.mark.parametrize("operacion", ["alta", "reenvio"])
async def test_un_smtp_colgado_vence_el_plazo_y_deja_la_transaccion_intacta(
    operacion: str,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)
    _hacer_que_send_mail_se_cuelgue(monkeypatch)
    caplog.set_level(logging.DEBUG)

    if operacion == "alta":
        salida: CreateUserOut | IssuedLinkOut = await _crear(
            session,
            email="colgado@test.apex",
            role="coach",
            by=admin.id,
            front_base_url=FRONT,
            settings=entorno.settings,
        )
        enlace = salida.activation_url if isinstance(salida, CreateUserOut) else ""
    else:
        salida = await _reenviar(
            session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
        )
        enlace = salida.url if isinstance(salida, IssuedLinkOut) else ""

    assert salida.email_sent is False
    texto = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert "TimeoutError" in texto
    assert token_del_cuerpo(enlace) not in texto
    await session.flush()  # la sesión sigue usable: el commit posterior funcionaría
    assert (await session.execute(text("select 1"))).scalar_one() == 1


@pytest.mark.parametrize("operacion", ["alta", "reenvio"])
async def test_un_error_de_base_al_leer_channels_se_propaga_y_no_emite_token(
    operacion: str,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)

    async def roto(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("select", {}, Exception("base caída"))

    monkeypatch.setattr(mail_texts.settings_service, "get", roto)

    with pytest.raises(OperationalError):
        if operacion == "alta":
            await _crear(
                session,
                email="roto@test.apex",
                role="coach",
                by=admin.id,
                front_base_url=FRONT,
                settings=entorno.settings,
            )
        else:
            await _reenviar(
                session,
                pendiente.id,
                by=admin.id,
                front_base_url=FRONT,
                settings=entorno.settings,
            )

    if operacion == "reenvio":
        assert await tokens_de(session, pendiente.id) == []
    assert entorno.smtp.mensajes == []


@pytest.mark.parametrize("operacion", ["alta", "reenvio"])
async def test_un_fallo_del_envio_no_deja_la_sesion_en_estado_fallido(
    operacion: str,
    monkeypatch: pytest.MonkeyPatch,
    api_prueba: FastAPI,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    admin = await usuario_real("admin")
    pendiente = await usuario_real("coach", password=None)
    entorno = await _preparar(monkeypatch, api_prueba, session, admin.id, smtp=True, canal=True)
    hacer_que_send_mail_lance(monkeypatch)

    if operacion == "alta":
        salida: CreateUserOut | IssuedLinkOut = await _crear(
            session,
            email="sesion-ok@test.apex",
            role="coach",
            by=admin.id,
            front_base_url=FRONT,
            settings=entorno.settings,
        )
    else:
        salida = await _reenviar(
            session, pendiente.id, by=admin.id, front_base_url=FRONT, settings=entorno.settings
        )

    assert salida.email_sent is False
    await session.flush()
    assert (await session.execute(text("select 1"))).scalar_one() == 1
