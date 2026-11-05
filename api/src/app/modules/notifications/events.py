"""Eventos que emite `notifications` (S5-B7; L7: se definen en el emisor y se re-exportan desde
`service.py`). Privado: los suscriptores los importan de `notifications.service`.

Solo ids, canal y fecha: ningún evento lleva nombres, teléfonos, correos, motivos ni mensajes de
error (S5-D24, S3-D70). `NotificationSkipped` NO lleva el motivo de la omisión.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from app.core.events import DomainEvent

ChannelName = Literal["email", "whatsapp_link"]


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationQueued(DomainEvent):
    """Una fila `pending` quedó insertada (solo las realmente nuevas; S5-D26)."""

    notification_id: UUID
    member_id: UUID
    rule_id: UUID
    channel: ChannelName
    target_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationSent(DomainEvent):
    """El aviso pasó a `sent` (el enlace de WhatsApp se abrió, o el correo salió)."""

    notification_id: UUID
    member_id: UUID
    channel: ChannelName


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationFailed(DomainEvent):
    """El aviso agotó sus intentos y quedó `failed`."""

    notification_id: UUID
    member_id: UUID
    channel: ChannelName


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationSkipped(DomainEvent):
    """El aviso se omitió. El motivo vive solo en la fila (`skip_reason`), nunca en el evento."""

    notification_id: UUID
    member_id: UUID
    channel: ChannelName
