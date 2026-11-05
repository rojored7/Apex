"""Puerto `NotificationChannel` (S5-D28). `ChannelPayload` lleva lo mínimo para un envío; su
`repr` no muestra el destinatario ni el cuerpo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ChannelPayload:
    to: str = field(repr=False)
    subject: str
    body: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChannelResult:
    """`error_code` es del conjunto cerrado de S5-D24 (`timeout`, `auth`, `refused`,
    `invalid_recipient`, `unknown`) o `None` si salió bien."""

    ok: bool
    error_code: str | None = None


class NotificationChannel(Protocol):
    name: str

    async def send(self, payload: ChannelPayload) -> ChannelResult: ...
