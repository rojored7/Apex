"""Comandos sobre cuentas: `seed`, `issue-reset-link` y `unlock-user` (implementación asíncrona).

Extraído de `cli.py` en B0 (S4B-D28) sin cambios de comportamiento; los comandos Typer siguen
en `cli.py`. Solo importa `cli_base`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import typer

from app.cli_base import (
    RuntimeOptions,
    cli_runtime,
    resolve_actor,
    unit_of_work,
)
from app.core.config import Settings


async def _seed(
    settings: Settings,
    admin_email: str,
    admin_password: str,
    actor_email: str | None,
    *,
    force_change: bool,
    options: RuntimeOptions | None = None,
) -> str:
    from app.core.security import configure_password_hasher, configure_password_policy
    from app.modules.auth.service import seed_admin

    configure_password_hasher(
        settings.ARGON2_TIME_COST, settings.ARGON2_MEMORY_COST_KIB, settings.ARGON2_PARALLELISM
    )
    configure_password_policy(settings.PASSWORD_MIN_LENGTH)
    async with cli_runtime(settings, options) as session:
        async with session.begin():
            actor = await resolve_actor(session, actor_email)
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            async with session.begin():
                resultado = await seed_admin(
                    session, admin_email, admin_password, by=actor, force_change=force_change
                )
    return resultado.outcome


# El mismo texto para un correo inexistente, borrado o no elegible: no revela si existe.
_LINK_REJECTED = "issue-reset-link: esa cuenta no puede recibir un enlace"


async def _issue_reset_link(
    settings: Settings, email: str, actor_email: str, options: RuntimeOptions | None = None
) -> tuple[str, str, str] | None:
    """`(url, propósito, vence)` o `None` si la cuenta no existe o no es elegible. Sale con 2
    (por `resolve_actor` o aquí) si `--as` no es un admin activo."""
    from app.modules.auth.exceptions import UserNotEligible, UserNotFound
    from app.modules.auth.service import issue_link

    async with cli_runtime(settings, options) as session:
        actor, objetivo = await _admin_actor_and_target(session, actor_email, email)
        if objetivo is None:
            return None
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            try:
                async with session.begin():
                    salida = await issue_link(
                        session, objetivo, by=actor, front_base_url=settings.FRONT_BASE_URL
                    )
            except (UserNotFound, UserNotEligible):
                return None
    return salida.url, salida.purpose, salida.expires_at.isoformat()


async def _admin_actor_and_target(
    session: Any, actor_email: str, email: str
) -> tuple[UUID, UUID | None]:
    """`(actor, objetivo)` en una transacción de lectura: `--as` debe ser un admin activo (sale
    con 2 si no) y el objetivo es el id vivo de `email` o `None` (sin revelar si existe)."""
    from app.modules.auth.service import (
        active_admin_id_by_email,
        ids_by_email,
        normalize_login_email,
    )

    async with session.begin():
        actor = await resolve_actor(session, actor_email)
        if await active_admin_id_by_email(session, actor_email) != actor:
            typer.echo("--as: debe ser un admin activo", err=True)
            raise typer.Exit(code=2)
        objetivo = (await ids_by_email(session, [email])).get(normalize_login_email(email))
    return actor, objetivo


# El mismo texto para una cuenta no bloqueada, inexistente o borrada: no revela si existe.
_UNLOCK_REJECTED = "unlock-user: no hay una cuenta bloqueada con ese correo"


async def _unlock_user(
    settings: Settings, email: str, actor_email: str, options: RuntimeOptions | None = None
) -> bool:
    """`True` si desbloqueó; `False` si la cuenta no existe, está borrada o no está bloqueada.
    Sale con 2 (por `resolve_actor` o aquí) si `--as` no es un admin activo."""
    from app.modules.auth.exceptions import NotLocked, UserNotFound
    from app.modules.auth.service import unlock

    async with cli_runtime(settings, options) as session:
        actor, objetivo = await _admin_actor_and_target(session, actor_email, email)
        if objetivo is None:
            return False
        # El actor debe seguir fijado durante el commit: la auditoría se escribe en el flush.
        with unit_of_work(actor):
            try:
                async with session.begin():
                    await unlock(session, objetivo, by=actor)
            except (UserNotFound, NotLocked):
                return False
    return True
