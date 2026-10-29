"""`verify-audit` (S4A-B3, US-105): implementación asíncrona y espera del candado.

Extraído de `cli.py` en B0 (S4B-D28) sin cambios de comportamiento; el comando Typer sigue en
`cli.py`. Solo importa `cli_base`.
"""

from __future__ import annotations

from typing import Any, Final

from app.cli_base import RuntimeOptions, cli_runtime, reject, resolve_actor, unit_of_work
from app.core.config import Settings

VERIFY_LOCK_POLL_S: Final = 2.0
"""Espera entre intentos de `pg_try_advisory_lock` de `verify-audit` (S4A-D15)."""


async def _verify_audit(
    settings: Settings, options: RuntimeOptions, actor_email: str | None, wait_timeout: int
) -> tuple[str, int]:
    """`(mensaje, código)`: espera el candado, verifica bajo el actor y confirma."""
    from app.core.audit_verify import format_verify_message, run_verification
    from app.modules.audit.service import release_verify_lock

    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        conn = await _wait_verify_lock(wait_timeout)
        try:
            with unit_of_work(actor):
                async with session.begin():
                    vista = await run_verification(session, source="cli", by=actor)
        finally:
            await release_verify_lock(conn)
    return format_verify_message(vista)


async def _wait_verify_lock(wait_timeout: int) -> Any:
    """La conexión del candado `4_270_003` (`AUTOCOMMIT`), reintentando cada
    `VERIFY_LOCK_POLL_S` segundos; sale con 2 si `wait_timeout` se agota."""
    import asyncio
    import time

    from app.modules.audit.service import acquire_verify_lock

    limite = time.monotonic() + wait_timeout
    while (conn := await acquire_verify_lock()) is None:
        restante = limite - time.monotonic()
        if restante <= 0:
            reject("otra verificación sigue en curso (--wait-timeout agotado)", "verify-audit")
        await asyncio.sleep(min(VERIFY_LOCK_POLL_S, restante))
    return conn
