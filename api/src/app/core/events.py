"""Bus de eventos en memoria dentro de la transacción (US-014). Stub: S0-B4."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

MAX_EVENT_DEPTH = 5


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime


E = TypeVar("E", bound=DomainEvent)
Handler = Callable[[E, AsyncSession], Awaitable[None]]


class EventDepthExceeded(RuntimeError):
    pass


def subscribe(event_type: type[E], handler: Handler[E]) -> None:
    raise NotImplementedError


def subscribers_for(event_type: type[DomainEvent]) -> tuple[Handler[Any], ...]:
    raise NotImplementedError


def clear_subscribers() -> None:
    raise NotImplementedError


async def emit(event: DomainEvent, session: AsyncSession) -> None:
    raise NotImplementedError
