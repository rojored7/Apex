"""CRUD de reglas de aviso (S5-B6, US-121; S5-D24, S5-D214). Privado: solo `service.py` lo importa.

- `create_rule` / `update_rule`: `validate_rule` sobre la regla RESULTANTE; la plantilla debe
  existir (422 `field=template_id`); una regla activa con el mismo disparador, desfase y canal es
  409 `duplicate_active_rule` con el id de la existente (la carrera la decide el único parcial
  `uq_notification_rules_active_key` dentro de un savepoint).
- `update_rule`: `FOR UPDATE`, aplica solo lo enviado; sin cambios no hay `flush` ni auditoría.
- `list_rules`: filtros `is_active`, `channel`, `trigger` y `q` (nombre); orden
  `offset_days, channel, id`.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Final
from uuid import UUID

from sqlalchemy import Text, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_actor
from app.core.db import violated_constraint
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.notifications.exceptions import (
    DuplicateActiveRule,
    RuleNotFound,
    RuleValidationError,
)
from app.modules.notifications.models import (
    RULE_ACTIVE_KEY_INDEX,
    NotificationRule,
    NotificationTemplate,
)
from app.modules.notifications.rules import validate_rule
from app.modules.notifications.schemas import RuleCreate, RuleFilters, RuleOut, RulePatch

logger = logging.getLogger("app.notifications")

_EDITABLES: Final = ("name", "trigger", "offset_days", "channel", "template_id", "is_active")


async def _ensure_template(session: AsyncSession, template_id: UUID) -> None:
    existe = await session.scalar(
        select(NotificationTemplate.id).where(NotificationTemplate.id == template_id)
    )
    if existe is None:
        raise RuleValidationError(message="La plantilla no existe.", field="template_id")


async def _active_id(
    session: AsyncSession,
    trigger: str,
    offset_days: int,
    channel: str,
    *,
    exclude: UUID | None = None,
) -> UUID | None:
    consulta = select(NotificationRule.id).where(
        NotificationRule.trigger == trigger,
        NotificationRule.offset_days == offset_days,
        NotificationRule.channel == channel,
        NotificationRule.is_active.is_(True),
    )
    if exclude is not None:
        consulta = consulta.where(NotificationRule.id != exclude)
    resultado: UUID | None = await session.scalar(consulta)
    return resultado


async def _flush_unique(session: AsyncSession, rule: NotificationRule) -> None:
    """`flush` en un savepoint; el choque del único parcial se traduce a 409 con el ganador."""
    clave = (rule.trigger, rule.offset_days, rule.channel)  # el rollback expira la fila
    regla_id = rule.id
    try:
        async with session.begin_nested():
            session.add(rule)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != RULE_ACTIVE_KEY_INDEX:
            raise
        logger.info("notifications: regla activa repetida")
        raise DuplicateActiveRule(await _active_id(session, *clave, exclude=regla_id)) from None


async def _get(session: AsyncSession, rule_id: UUID, *, lock: bool) -> NotificationRule:
    consulta = select(NotificationRule).where(NotificationRule.id == rule_id)
    if lock:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    regla = await session.scalar(consulta)
    if regla is None:
        raise RuleNotFound()
    return regla


async def list_rules(
    session: AsyncSession, filters: RuleFilters, page: PageParams
) -> Page[RuleOut]:
    consulta = select(NotificationRule)
    if filters.is_active is not None:
        consulta = consulta.where(NotificationRule.is_active.is_(filters.is_active))
    if filters.channel is not None:
        consulta = consulta.where(NotificationRule.channel == filters.channel)
    if filters.trigger is not None:
        consulta = consulta.where(NotificationRule.trigger == filters.trigger)
    termino = clean_query(filters.q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(sql_fold(NotificationRule.name).ilike(patron, escape=LIKE_ESCAPE))
    consulta = consulta.order_by(
        NotificationRule.offset_days, NotificationRule.channel, NotificationRule.id
    )
    filas, total = await paginate(session, consulta, page)
    return to_page([RuleOut.model_validate(f) for f in filas], total, page)


async def get_rule(session: AsyncSession, rule_id: UUID) -> RuleOut:
    return RuleOut.model_validate(await _get(session, rule_id, lock=False))


async def create_rule(session: AsyncSession, data: RuleCreate) -> RuleOut:
    validate_rule(data.trigger, data.offset_days, data.channel)
    await _ensure_template(session, data.template_id)
    if data.is_active:
        existente = await _active_id(session, data.trigger, data.offset_days, data.channel)
        if existente is not None:
            raise DuplicateActiveRule(existente)
    regla = NotificationRule(
        name=unicodedata.normalize("NFC", data.name).strip(),
        trigger=data.trigger,
        offset_days=data.offset_days,
        channel=data.channel,
        template_id=data.template_id,
        is_active=data.is_active,
        created_by=get_actor(),
    )
    await _flush_unique(session, regla)
    logger.info("notifications: regla creada", extra={"rule_id": str(regla.id)})
    return RuleOut.model_validate(regla)


async def update_rule(session: AsyncSession, rule_id: UUID, data: RulePatch) -> RuleOut:
    regla = await _get(session, rule_id, lock=True)
    enviados = {
        campo: valor
        for campo in _EDITABLES
        if campo in data.model_fields_set and (valor := getattr(data, campo)) is not None
    }
    if "name" in enviados:
        enviados["name"] = unicodedata.normalize("NFC", enviados["name"]).strip()
    cambios = {c: v for c, v in enviados.items() if getattr(regla, c) != v}
    if not cambios:
        return RuleOut.model_validate(regla)
    final = {c: cambios.get(c, getattr(regla, c)) for c in _EDITABLES}
    validate_rule(final["trigger"], final["offset_days"], final["channel"])
    if "template_id" in cambios:
        await _ensure_template(session, cambios["template_id"])
    if final["is_active"] and cambios.keys() & {"trigger", "offset_days", "channel", "is_active"}:
        ocupante = await _active_id(
            session, final["trigger"], final["offset_days"], final["channel"], exclude=rule_id
        )
        if ocupante is not None:
            raise DuplicateActiveRule(ocupante)
    for campo, valor in cambios.items():
        setattr(regla, campo, valor)
    await _flush_unique(session, regla)
    logger.info(
        "notifications: regla editada",
        extra={"rule_id": str(rule_id), "rule_fields": sorted(cambios)},
    )
    return RuleOut.model_validate(regla)
