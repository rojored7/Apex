"""Contexto de la petición y del actor (G-01, US-016, N-15). Solo biblioteca estándar.

Vive en un archivo neutro para que `core/audit.py`, `core/crypto` (US-029) y
`core/security` (US-034) lo lean sin importarse entre sí.

- `request_id_var`: id de la petición (US-017, US-018).
- `SYSTEM_USER_ID`: el usuario técnico `system@apex.local` (N-15). Es una constante, no
  una variable de entorno: nadie puede inyectar otro actor técnico. Lo usan el worker, el
  seed, la importación y las migraciones de proveedor como `created_by`. Todo comando del
  CLI acepta `--as <email>` para atribuir la acción a una persona.
- `current_actor` / `get_actor()`: el usuario que escribe. Sin actor, cualquier flush de un
  modelo con `created_by` o auditado falla con `MissingActorError`: nunca hay auditoría
  silenciosa con actor vacío.

Reglas de propagación:
- Por HTTP, `current_user` (US-034) es una dependencia `async def` que llama a
  `current_actor.set(user.id)` y **no** lo resetea en un teardown. Cada petición corre en
  su propia tarea con su propio contexto, y el commit de `get_session` (pedida como
  `SessionDep`, alcance de función: antes de enviar la respuesta, N-1) ocurre en el
  teardown de esa dependencia; como `current_user` depende de `get_session`, su teardown
  corre antes, y si reseteara el actor ahí el commit se quedaría sin actor.
- Las rutas sin token que escriben tablas auditadas (login con bloqueo, `reset` y
  activación de contraseña, EP-04) fijan el actor de forma explícita con `actor_scope`.
- Worker y CLI: `with actor_scope(SYSTEM_USER_ID):` o el actor de `--as`, y
  `batch_scope(uuid4())` por comando o job: las operaciones del bus comparten `batch_id`
  en `crypto_ops` (US-029).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final
from uuid import UUID

SYSTEM_USER_ID: Final[UUID] = UUID("00000000-0000-0000-0000-000000000001")

request_id_var: ContextVar[str | None] = ContextVar("apex_request_id", default=None)
current_actor: ContextVar[UUID | None] = ContextVar("apex_actor", default=None)
current_batch: ContextVar[UUID | None] = ContextVar("apex_batch", default=None)

MISSING_ACTOR_MESSAGE: Final = "falta el actor: fije actor_scope(SYSTEM_USER_ID) o --as <email>"


class MissingActorError(RuntimeError):
    """No hay actor en el contexto y se intentó escribir una tabla con actor."""

    def __init__(self, message: str = MISSING_ACTOR_MESSAGE) -> None:
        super().__init__(message)


def get_actor() -> UUID:
    """El actor del contexto; lanza `MissingActorError` si no hay."""
    actor = current_actor.get()
    if actor is None:
        raise MissingActorError
    return actor


@contextmanager
def actor_scope(user_id: UUID) -> Iterator[None]:
    """Fija el actor dentro del bloque y restaura el anterior al salir."""
    token = current_actor.set(user_id)
    try:
        yield
    finally:
        current_actor.reset(token)


@contextmanager
def batch_scope(batch_id: UUID) -> Iterator[None]:
    """Fija el lote de la unidad de trabajo (comando del CLI, job del worker)."""
    token = current_batch.set(batch_id)
    try:
        yield
    finally:
        current_batch.reset(token)
