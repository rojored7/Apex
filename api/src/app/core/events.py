"""Bus de eventos en memoria dentro de la transacción (US-014).

- Los eventos son dataclasses congeladas que heredan de `DomainEvent`; se declaran
  en el `service.py` del módulo emisor (su contrato público) y el suscriptor los
  importa desde ahí. Cada módulo se suscribe al importarse su `service.py`;
  `main.load_module_services()` los importa en el api, el worker y el CLI.
- `emit(event, session)` ejecuta los handlers en orden de registro, con la misma
  sesión, y propaga cualquier excepción: si un handler falla, la transacción del
  emisor se revierte entera. Nada corre "después del commit" (N-37): un efecto
  obligatorio se persiste en una tabla dentro de la misma transacción.
- Cuando dos services se usan mutuamente, se importan como módulo
  (`from app.modules.payments import service as payments_service`) y se accede a
  sus atributos al llamar, nunca `from ... import Nombre` en el nivel superior.
- Si se loguea un evento, solo su tipo: su contenido puede llevar datos del socio.

Este módulo importa solo `core/clock.py` y el tipo `AsyncSession`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock

MAX_EVENT_DEPTH = 5


def _ahora() -> datetime:
    return current_clock().now_utc()


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Base de todo evento. `occurred_at` sale del reloj actual (Q28)."""

    occurred_at: datetime = field(default_factory=_ahora)


type Handler[E: DomainEvent] = Callable[[E, AsyncSession], Awaitable[None]]


class EventDepthExceeded(RuntimeError):
    """Una cadena de eventos superó `MAX_EVENT_DEPTH`; el 500 lo traduce US-017."""


_subscribers: dict[type[DomainEvent], list[Handler[Any]]] = {}
_depth: ContextVar[int] = ContextVar("apex_event_depth", default=0)


def subscribe[E: DomainEvent](event_type: type[E], handler: Handler[E]) -> None:
    """Registra un handler para un tipo exacto. Idempotente."""
    handlers = _subscribers.setdefault(event_type, [])
    if handler not in handlers:
        handlers.append(handler)


def subscribers_for(event_type: type[DomainEvent]) -> tuple[Handler[Any], ...]:
    return tuple(_subscribers.get(event_type, ()))


def clear_subscribers() -> None:
    """Solo para pruebas."""
    _subscribers.clear()


async def emit(event: DomainEvent, session: AsyncSession) -> None:
    """Ejecuta los handlers del tipo exacto del evento, en orden, con la misma sesión."""
    handlers = _subscribers.get(type(event))
    if not handlers:
        return
    profundidad = _depth.get()
    if profundidad >= MAX_EVENT_DEPTH:
        raise EventDepthExceeded(
            f"cadena de eventos de más de {MAX_EVENT_DEPTH} niveles al emitir "
            f"{type(event).__name__}"
        )
    token = _depth.set(profundidad + 1)
    try:
        for handler in list(handlers):
            await handler(event, session)
    finally:
        _depth.reset(token)
