"""Canal de correo (S5-B7 la firma; B8 lo implementa sobre `core.mail`; S5-D28)."""

from __future__ import annotations

from typing import Final

from app.modules.notifications.channels.base import ChannelPayload, ChannelResult


class EmailChannel:
    name: Final = "email"

    async def send(self, payload: ChannelPayload) -> ChannelResult:
        raise NotImplementedError("S5-B8: EmailChannel.send")
