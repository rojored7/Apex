"""Consultas de elegibilidad del envío de avisos (S9-V7b, L7: salen de `sending.py`, que medía 800
líneas). Privado: solo `sending.py` lo importa; sin lógica de envío ni candados de aviso en vuelo.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.models import Notification
from app.modules.notifications.queries import PENDING_WINDOW_DAYS

SessionFactory = async_sessionmaker[AsyncSession]


def eligible(today: date, max_attempts: int) -> ColumnElement[bool]:
    return and_(
        Notification.channel == "email",
        Notification.attempts < max_attempts,
        or_(
            and_(
                Notification.status == "pending",
                Notification.target_date <= today,
                Notification.target_date >= today - timedelta(days=PENDING_WINDOW_DAYS),
            ),
            and_(Notification.status == "failed", Notification.target_date <= today),
        ),
    )


async def eligible_ids(
    sf: SessionFactory, today: date, max_attempts: int
) -> list[tuple[UUID, int]]:
    """`(id, attempts)` de lo elegible: `attempts` es la versión que `_lock_eligible` exige."""
    async with sf() as session:
        filas = await session.execute(
            select(Notification.id, Notification.attempts)
            .where(eligible(today, max_attempts))
            .order_by(Notification.target_date, Notification.created_at, Notification.id)
        )
        return [(fila.id, fila.attempts) for fila in filas]


async def count_eligible(sf: SessionFactory, today: date, max_attempts: int) -> int:
    async with sf() as session:
        total = await session.scalar(
            select(func.count()).select_from(Notification).where(eligible(today, max_attempts))
        )
    return int(total or 0)


async def lock_eligible(
    session: AsyncSession,
    notification_id: UUID,
    expected_attempts: int,
    today: date,
    max_attempts: int,
) -> Notification | None:
    """La fila, si sigue elegible, nadie más la tiene (`SKIP LOCKED`) y ninguna otra pasada ya
    contó un intento (`attempts == expected_attempts`, S9-D44); `None` si no."""
    return await session.scalar(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.attempts == expected_attempts,
            eligible(today, max_attempts),
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
