"""`EmailChannel` sobre `core.mail` (US-125; S5-D28, S5-D205). # Rojo B8

Texto plano siempre; `reply_to` y `from_name` salen del `ChannelPayload`; `configured` es
`mail_configured(settings)`; nunca lanza (todo fallo es un `ChannelResult` con código cerrado) y
el `repr` del payload no muestra destinatario ni cuerpo. Sin base de datos.
"""

from __future__ import annotations

import smtplib

import pytest

from app.core.mail import MAIL_ERROR_CODES
from app.modules.notifications.channels.base import ChannelPayload
from app.modules.notifications.channels.email import EmailChannel
from tests.core._canales_apoyo import SMTP_COMPLETO, instalar_smtp, settings_canales

DESTINO = "lucia.gomez@example.com"


def _canal(**cambios: object) -> EmailChannel:
    return EmailChannel(settings_canales(**{**SMTP_COMPLETO, **cambios}))


def _payload(**cambios: object) -> ChannelPayload:
    base = {"to": DESTINO, "subject": "Tu membresía vence pronto", "body": "Hola Lucía, vence hoy."}
    return ChannelPayload(**{**base, **cambios})  # type: ignore[arg-type]


def test_el_canal_se_llama_email() -> None:
    assert EmailChannel.name == "email"


def test_configured_es_verdadero_con_servidor_y_remitente() -> None:
    assert _canal().configured is True


def test_configured_es_falso_sin_smtp() -> None:
    assert EmailChannel(settings_canales()).configured is False


async def test_envia_un_correo_de_texto_plano_con_asunto_y_cuerpo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = instalar_smtp(monkeypatch)

    resultado = await _canal().send(_payload())

    assert (resultado.ok, resultado.error_code) == (True, None)
    (mensaje,) = smtp.mensajes
    assert mensaje["To"] == DESTINO and mensaje["Subject"] == "Tu membresía vence pronto"
    assert mensaje.get_content_type() == "text/plain"
    assert "Hola Lucía, vence hoy." in mensaje.get_content()
    assert not mensaje.is_multipart()


async def test_reply_to_y_nombre_del_remitente_viajan_en_las_cabeceras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = instalar_smtp(monkeypatch)

    await _canal().send(_payload(reply_to="hola@gimnasio.test", from_name="APEX CrossFit"))

    (mensaje,) = smtp.mensajes
    assert mensaje["Reply-To"] == "hola@gimnasio.test"
    assert "APEX CrossFit" in mensaje["From"] and SMTP_COMPLETO["SMTP_FROM"] in mensaje["From"]


async def test_sin_reply_to_no_pone_la_cabecera(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp = instalar_smtp(monkeypatch)
    await _canal().send(_payload())
    assert smtp.mensajes[0]["Reply-To"] is None


@pytest.mark.parametrize(
    ("fallo", "codigo"),
    [
        (TimeoutError(), "timeout"),
        (smtplib.SMTPAuthenticationError(535, b"mala clave"), "auth"),
        (smtplib.SMTPRecipientsRefused({DESTINO: (550, b"no")}), "refused"),
        (RuntimeError("error raro con lucia.gomez@example.com"), "unknown"),
    ],
)
async def test_un_fallo_de_smtp_devuelve_un_codigo_cerrado_y_no_lanza(
    monkeypatch: pytest.MonkeyPatch, fallo: BaseException, codigo: str
) -> None:
    smtp = instalar_smtp(monkeypatch)
    smtp.fallo = fallo

    resultado = await _canal().send(_payload())

    assert (resultado.ok, resultado.error_code) == (False, codigo)
    assert resultado.error_code in MAIL_ERROR_CODES


async def test_un_destinatario_invalido_es_invalid_recipient_sin_conectar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp = instalar_smtp(monkeypatch)
    resultado = await _canal().send(_payload(to="no-es-un-correo"))
    assert (resultado.ok, resultado.error_code) == (False, "invalid_recipient")
    assert smtp.conexiones == []


async def test_un_asunto_con_salto_de_linea_no_sale(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp = instalar_smtp(monkeypatch)
    resultado = await _canal().send(_payload(subject="Hola\r\nBcc: otro@example.com"))
    assert resultado.ok is False and resultado.error_code == "unknown"
    assert smtp.mensajes == []


async def test_sin_smtp_configurado_falla_sin_conectar(monkeypatch: pytest.MonkeyPatch) -> None:
    smtp = instalar_smtp(monkeypatch)
    resultado = await EmailChannel(settings_canales()).send(_payload())
    assert (resultado.ok, resultado.error_code) == (False, "unknown")
    assert smtp.conexiones == []


def test_el_repr_del_payload_no_muestra_destinatario_cuerpo_ni_reply_to() -> None:
    texto = repr(_payload(reply_to="hola@gimnasio.test"))
    for oculto in (DESTINO, "Hola Lucía", "hola@gimnasio.test"):
        assert oculto not in texto
