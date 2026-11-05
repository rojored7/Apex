"""Texto fijo de los correos de cuenta (S5-B9, US-131; S5-D37, N-36). Privado de `auth`.

Texto plano en español, sin HTML, sin retornos de carro y sin datos del socio: lo único que cambia
entre dos correos del mismo tipo es el enlace y el nombre del remitente del canal. Lo usan
`users.create_user` y `links.resend_link` / `links.forgot_deliver`.
"""

from __future__ import annotations

from typing import Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.mail import MailMessage, mail_configured

# Arista `auth → settings` del grafo de services (S2-D53): lee `channels`.
from app.modules.settings import service as settings_service
from app.modules.settings.schemas import ChannelsSettings, SectionKey

_ASUNTO_ACTIVACION: Final = "Activa tu cuenta en {remitente}"
_CUERPO_ACTIVACION: Final = (
    "Hola.\n"
    "\n"
    "{remitente} creó una cuenta para ti. Para activarla y elegir tu contraseña, abre este "
    "enlace:\n"
    "\n"
    "{url}\n"
    "\n"
    "El enlace sirve una sola vez y vence en 72 horas. Si no esperabas este mensaje, ignóralo.\n"
)

_ASUNTO_RECUPERACION: Final = "Restablece tu contraseña en {remitente}"
_CUERPO_RECUPERACION: Final = (
    "Hola.\n"
    "\n"
    "Recibimos una solicitud para restablecer tu contraseña en {remitente}. Para elegir una "
    "nueva, abre este enlace:\n"
    "\n"
    "{url}\n"
    "\n"
    "El enlace sirve una sola vez y vence pronto. Si no lo pediste, ignora este mensaje: tu "
    "contraseña actual no cambia.\n"
)


def activation_mail(url: str, sender: str) -> tuple[str, str]:
    """Asunto y cuerpo del correo de activación de una cuenta nueva."""
    return (
        _ASUNTO_ACTIVACION.format(remitente=sender),
        _CUERPO_ACTIVACION.format(remitente=sender, url=url),
    )


def reset_mail(url: str, sender: str) -> tuple[str, str]:
    """Asunto y cuerpo del correo de recuperación de contraseña."""
    return (
        _ASUNTO_RECUPERACION.format(remitente=sender),
        _CUERPO_RECUPERACION.format(remitente=sender, url=url),
    )


async def email_sender_name(session: AsyncSession, settings: Settings) -> str | None:
    """El nombre del remitente de `channels.email` si el correo puede salir (SMTP configurado y
    canal habilitado); `None` si no (S5-D235: sin canal no se envía ni se emite token)."""
    if not mail_configured(settings):
        return None
    valor = await settings_service.get(session, SectionKey.channels)
    if not isinstance(valor, ChannelsSettings) or not valor.email.enabled:
        return None
    return valor.email.sender_name


def account_message(
    kind: Literal["activate", "reset"], *, to: str, url: str, sender: str
) -> MailMessage:
    """El correo de cuenta listo para `send_mail`: activación (`activate`) o recuperación."""
    construir = activation_mail if kind == "activate" else reset_mail
    asunto, cuerpo = construir(url, sender)
    return MailMessage(to=to, subject=asunto, body=cuerpo, from_name=sender)
