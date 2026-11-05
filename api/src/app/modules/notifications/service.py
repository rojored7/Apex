"""Fachada de `notifications` (S5-B6, US-120 y US-121; S5-D23): lo único que importan otros
módulos, el worker y el CLI.

- Plantillas: `list_templates`, `get_template`, `create_template` (409 `template_name_taken`),
  `update_template`, `preview`.
- Reglas: `list_rules`, `get_rule`, `create_rule` y `update_rule` (409 `duplicate_active_rule`).
- `seed_defaults(session) -> SeedResult`: dos plantillas y cinco reglas por defecto (S5-D25),
  idempotente y auditada. Las plantillas se igualan por nombre y las reglas por
  `(trigger, offset_days, channel)` sin mirar nombre ni estado (S5-D214): lo que ya existe no se
  toca, no se reactiva y no se duplica. Solo inserta; la auditoría la escribe el listener.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_actor
from app.modules.notifications.exceptions import SeedInProgress
from app.modules.notifications.models import NotificationRule, NotificationTemplate
from app.modules.notifications.rules import DEFAULT_CHANNEL, DEFAULT_RULES, DEFAULT_TEMPLATES
from app.modules.notifications.rules_crud import (
    create_rule,
    get_rule,
    list_rules,
    update_rule,
)
from app.modules.notifications.schemas import SeedResult
from app.modules.notifications.templates import (
    create_template,
    get_template,
    list_templates,
    preview,
    update_template,
)

logger = logging.getLogger("app.notifications")

SEED_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(hashtext(:k))"
SEED_LOCK_KEY: Final = "apex:seed:notifications"

__all__ = [
    "SeedResult",
    "create_rule",
    "create_template",
    "get_rule",
    "get_template",
    "list_rules",
    "list_templates",
    "preview",
    "seed_defaults",
    "update_rule",
    "update_template",
]


async def seed_defaults(session: AsyncSession) -> SeedResult:
    """Crea lo que falte de las plantillas y reglas por defecto; la segunda corrida da `(0, 0)`.
    El actor lo pone quien llama (`unit_of_work` del CLI); `created_by` es `get_actor()`.

    Toma `pg_advisory_xact_lock(hashtext('apex:seed:notifications'))` al inicio (S5-D215): dos
    siembras a la vez se serializan y la segunda ve lo que creó la primera. Un `IntegrityError`
    residual es `SeedInProgress` (409, texto fijo, reintentable)."""
    await session.execute(text(SEED_LOCK_SQL), {"k": SEED_LOCK_KEY})
    try:
        return await _seed(session, get_actor())
    except IntegrityError:
        logger.warning("notifications: la siembra chocó con otra concurrente")
        raise SeedInProgress from None


async def _seed(session: AsyncSession, actor: UUID) -> SeedResult:
    consulta = select(NotificationTemplate.name, NotificationTemplate.id)
    ids = {nombre: plantilla_id for nombre, plantilla_id in (await session.execute(consulta)).all()}
    plantillas_creadas = 0
    for nombre, (asunto, cuerpo) in DEFAULT_TEMPLATES.items():
        if nombre in ids:
            continue
        plantilla = NotificationTemplate(name=nombre, subject=asunto, body=cuerpo, created_by=actor)
        session.add(plantilla)
        await session.flush()
        ids[nombre] = plantilla.id
        plantillas_creadas += 1
    claves_q = select(
        NotificationRule.trigger, NotificationRule.offset_days, NotificationRule.channel
    )
    claves = {tuple(f) for f in (await session.execute(claves_q)).all()}
    reglas_creadas = 0
    for definida in DEFAULT_RULES:
        if (definida.trigger, definida.offset_days, DEFAULT_CHANNEL) in claves:
            continue
        session.add(
            NotificationRule(
                name=definida.name,
                trigger=definida.trigger,
                offset_days=definida.offset_days,
                channel=DEFAULT_CHANNEL,
                template_id=ids[definida.template],
                is_active=True,
                created_by=actor,
            )
        )
        reglas_creadas += 1
    await session.flush()
    logger.info(
        "notifications: siembra",
        extra={"templates_created": plantillas_creadas, "rules_created": reglas_creadas},
    )
    return SeedResult(templates_created=plantillas_creadas, rules_created=reglas_creadas)
