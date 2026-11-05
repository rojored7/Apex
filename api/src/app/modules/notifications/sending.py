"""Envío de avisos pendientes (S5-B7 la firma; B8 la implementa; S5-D28, S5-D35). Privado.

`send_pending(session_factory, today, *, load_contact)`: recorre los `pending` y `failed` con
intentos disponibles y los manda por su canal. `load_contact` se inyecta desde `service.py` (único
llamador de `contact_for_notification`, S5-D32).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.members.service import Contact
from app.modules.notifications.schemas import SendResult

LoadContact = Callable[[AsyncSession, UUID], Awaitable[Contact]]


async def send_pending(
    session_factory: async_sessionmaker[AsyncSession],
    today: date,
    *,
    load_contact: LoadContact,
) -> SendResult:
    raise NotImplementedError("S5-B8: sending.send_pending")
