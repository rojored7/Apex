"""Correo saliente por SMTP con `smtplib` (S5-B4; S5-D64, S5-D205, M-7).

- `MailMessage(to, subject, body, reply_to=None, from_name=None)`: su `repr` omite `to`, `body` y
  `reply_to` (direcciones y contenido de personas nunca llegan a un log).
- `MailResult(ok, error_code)` con `error_code` en `MAIL_ERROR_CODES` o `None`.
- `send_mail(settings, message)`: `smtplib.SMTP` en `asyncio.to_thread` con
  `timeout=NOTIFY_NET_TIMEOUT_S`, `starttls(context=ssl.create_default_context())` (verifica el
  certificado y el nombre del servidor), `EmailMessage` de texto plano (nunca HTML) y cabeceras
  sin saltos de línea. Nunca propaga: todo fallo es un `MailResult(False, <código>)`.
- S5-D205: sin SMTP configurado, o con `none` fuera de `ENV=dev`, devuelve `unknown` SIN
  conectar; una cabecera con `\r` o `\n` devuelve `unknown` (línea fija `cabecera rechazada`);
  un destinatario inválido, `invalid_recipient`. Con `none` (solo desarrollo) no se envía el
  usuario ni la clave: no viajan sin cifrar.
- El log lleva líneas fijas y, como mucho, el tipo de la excepción: jamás direcciones, asunto,
  cuerpo ni credenciales, ni traza.

Único archivo de `app` que importa `smtplib`. No importa `app.modules`, `core.audit`, `core.db`
ni `core.crypto`.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Final

from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.core.validators import EmailAddress

logger = logging.getLogger("app.mail")

MAIL_ERROR_CODES: Final[tuple[str, ...]] = (
    "timeout",
    "auth",
    "refused",
    "invalid_recipient",
    "unknown",
)

_ADAPTADOR_CORREO: Final[TypeAdapter[str]] = TypeAdapter(EmailAddress)
# CR, LF, los separadores de línea de Unicode (U+2028, U+2029) y NEL (U+0085): LOW 2.
_SALTOS: Final[tuple[str, ...]] = ("\r", "\n", "\u2028", "\u2029", "\x85")


@dataclass(frozen=True)
class MailMessage:
    """Un correo de texto plano. El `repr` omite `to`, `body` y `reply_to`."""

    to: str = field(repr=False)
    subject: str
    body: str = field(repr=False)
    reply_to: str | None = field(default=None, repr=False)
    from_name: str | None = None


@dataclass(frozen=True)
class MailResult:
    """Resultado de un envío: `ok` o un `error_code` de `MAIL_ERROR_CODES`."""

    ok: bool
    error_code: str | None = None


def mail_configured(settings: Settings) -> bool:
    """Hay servidor y remitente (la regla todo-o-nada de `Settings` completa el resto)."""
    return bool(settings.SMTP_HOST) and bool(settings.SMTP_FROM)


def _tiene_saltos(*valores: str | None) -> bool:
    return any(v is not None and any(s in v for s in _SALTOS) for v in valores)


def _destinatario(valor: str) -> str | None:
    try:
        return _ADAPTADOR_CORREO.validate_python(valor)
    except ValidationError:
        return None


def _armar(settings: Settings, message: MailMessage, destino: str) -> EmailMessage | None:
    """El mensaje listo o `None` si una cabecera no es admisible (sin decir cuál)."""
    if _tiene_saltos(message.subject, message.from_name, message.reply_to):
        return None
    remitente = settings.SMTP_FROM or ""
    respuesta = None
    if message.reply_to is not None:
        respuesta = _destinatario(message.reply_to)
        if respuesta is None:
            return None
    try:
        correo = EmailMessage()
        correo["From"] = str(Address(display_name=message.from_name or "", addr_spec=remitente))
        correo["To"] = destino
        correo["Subject"] = message.subject
        if respuesta is not None:
            correo["Reply-To"] = respuesta
        correo.set_content(message.body)
    except (ValueError, TypeError):
        return None
    return correo


def _enviar_bloqueante(settings: Settings, correo: EmailMessage) -> None:
    """Corre en un hilo (`smtplib` bloquea). STARTTLS con contexto por defecto antes del login."""
    cifrado = settings.SMTP_TLS_MODE == "starttls"
    with smtplib.SMTP(
        settings.SMTP_HOST or "", settings.SMTP_PORT, timeout=settings.NOTIFY_NET_TIMEOUT_S
    ) as conexion:
        conexion.ehlo()
        if cifrado:
            conexion.starttls(context=ssl.create_default_context())
            conexion.ehlo()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                conexion.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
        conexion.send_message(correo)


def _codigo_de(error: Exception) -> str:
    """Del tipo de la excepción al código; el orden importa (`SMTPException` es `OSError`)."""
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "auth"
    if isinstance(error, smtplib.SMTPRecipientsRefused | smtplib.SMTPSenderRefused):
        return "refused"
    return "unknown"


def _fallo(codigo: str, linea: str) -> MailResult:
    logger.warning(linea, extra={"mail_error": codigo})
    return MailResult(ok=False, error_code=codigo)


async def send_mail(settings: Settings, message: MailMessage) -> MailResult:
    """Envía `message`; nunca lanza (S5-D205)."""
    if not mail_configured(settings):
        return _fallo("unknown", "correo no configurado")
    if settings.SMTP_TLS_MODE != "starttls" and settings.ENV != "dev":
        return _fallo("unknown", "envio sin cifrar rechazado fuera de dev")
    destino = _destinatario(message.to)
    if destino is None:
        return _fallo("invalid_recipient", "destinatario invalido")
    correo = _armar(settings, message, destino)
    if correo is None:
        return _fallo("unknown", "cabecera rechazada")
    try:
        await asyncio.to_thread(_enviar_bloqueante, settings, correo)
    except Exception as error:
        codigo = _codigo_de(error)
        logger.warning(
            "correo no enviado",
            extra={"mail_error": codigo, "error_type": type(error).__name__},
        )
        return MailResult(ok=False, error_code=codigo)
    return MailResult(ok=True)
