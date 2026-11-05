"""Canal de correo (S5-B8; S5-D28) sobre `core.mail`.

`EmailChannel(settings)` envuelve `core.mail.send_mail(settings, MailMessage(...))` con `reply_to` y
`from_name` del `ChannelPayload` (los lee `sending` de `settings.channels.email`), siempre texto
plano. `configured` es `mail_configured(settings)`. Nunca lanza: todo fallo es un
`ChannelResult(False, <código de MAIL_ERROR_CODES>)`.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.mail import MailMessage, mail_configured, send_mail
from app.modules.notifications.channels.base import ChannelPayload, ChannelResult


class EmailChannel:
    name: str = "email"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return mail_configured(self._settings)

    async def send(self, payload: ChannelPayload) -> ChannelResult:
        resultado = await send_mail(
            self._settings,
            MailMessage(
                to=payload.to,
                subject=payload.subject,
                body=payload.body,
                reply_to=payload.reply_to,
                from_name=payload.from_name,
            ),
        )
        return ChannelResult(ok=resultado.ok, error_code=resultado.error_code)
