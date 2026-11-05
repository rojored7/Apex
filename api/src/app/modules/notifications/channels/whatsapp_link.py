"""Canal `whatsapp_link` (S5-D28): no envía nada; existe para que la regla de canal sea un solo
punto. El aviso pasa a `sent` cuando el usuario abre el enlace (`service.wa_link`)."""

from __future__ import annotations

from typing import Final

from app.modules.notifications.channels.base import ChannelPayload, ChannelResult


class WhatsAppLinkChannel:
    name: Final = "whatsapp_link"

    @property
    def configured(self) -> bool:
        return False  # no envía: el usuario abre el enlace

    async def send(self, payload: ChannelPayload) -> ChannelResult:
        raise NotImplementedError("S5-B7 Verde: WhatsAppLinkChannel.send")
