"""Contexto de la petición y del actor (G-01). Solo biblioteca estándar.

Primera versión (S0-B3, US-017 y US-018): `request_id_var`. US-016 agrega
`SYSTEM_USER_ID`, `current_actor()`, `current_batch()`, `actor_scope()` y
`batch_scope()`.
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("apex_request_id", default=None)
