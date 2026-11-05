"""Fachada de `notifications` (S5-B6, US-120 y US-121; S5-D23): lo único que importan otros
módulos, el worker y el CLI.

- Plantillas: `list_templates`, `get_template`, `create_template` (409 `template_name_taken`),
  `update_template`, `preview`.
- Reglas: `list_rules`, `get_rule`, `create_rule` y `update_rule` (409 `duplicate_active_rule`).
- `seed_defaults(session) -> SeedResult`: dos plantillas y cinco reglas por defecto (S5-D25),
  idempotente y auditada. Las plantillas se igualan por nombre y las reglas por
  `(trigger, offset_days, channel)` sin mirar nombre ni estado (S5-D214): lo que ya existe no se
  toca, no se reactiva y no se duplica. Solo inserta; la auditoría la escribe el listener.
- S5-B7 (US-124, US-127 a US-130): `generate_today` (avisos del día, idempotente), `today_list`,
  `today_count`, `list`, `get`, `list_for_member`, `wa_link` (descifra el teléfono con
  `members.service.contact_for_notification`, el ÚNICO llamador, S5-D32; marca `sent` una sola
  vez) y `skip` (motivo de 3 a 500). Los cuatro eventos se definen en `events.py` y salen de aquí.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.modules.members import service as members_service
from app.modules.notifications.events import (
    NotificationFailed,
    NotificationQueued,
    NotificationSent,
    NotificationSkipped,
)
from app.modules.notifications.exceptions import (
    InvalidPhone,
    MemberWithoutPhone,
    NotificationClosed,
    NotificationNotFound,
    SeedInProgress,
    WrongChannel,
)
from app.modules.notifications.generate import generate_today
from app.modules.notifications.models import (
    Notification,
    NotificationRule,
    NotificationTemplate,
)
from app.modules.notifications.queries import get, list_for_member, today_count, today_list
from app.modules.notifications.queries import list_ as list
from app.modules.notifications.rules import (
    DEFAULT_CHANNEL,
    DEFAULT_RULES,
    DEFAULT_TEMPLATES,
    can_skip,
)
from app.modules.notifications.rules_crud import (
    create_rule,
    get_rule,
    list_rules,
    update_rule,
)
from app.modules.notifications.schemas import NotificationOut, SeedResult, WaLinkOut
from app.modules.notifications.templates import (
    create_template,
    get_template,
    list_templates,
    preview,
    update_template,
)
from app.modules.notifications.whatsapp import build_link

logger = logging.getLogger("app.notifications")

SEED_LOCK_SQL: Final = "SELECT pg_advisory_xact_lock(hashtext(:k))"
SEED_LOCK_KEY: Final = "apex:seed:notifications"

__all__ = [
    "NotificationFailed",
    "NotificationQueued",
    "NotificationSent",
    "NotificationSkipped",
    "SeedResult",
    "create_rule",
    "create_template",
    "generate_today",
    "get",
    "get_rule",
    "get_template",
    "list",
    "list_for_member",
    "list_rules",
    "list_templates",
    "preview",
    "seed_defaults",
    "skip",
    "today_count",
    "today_list",
    "update_rule",
    "update_template",
    "wa_link",
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


async def wa_link(session: AsyncSession, notification_id: UUID, by: UUID) -> WaLinkOut:
    """El enlace de WhatsApp del aviso y su marca de `sent` (S5-D27, S5-D59, M-9).

    409 `notification_closed` si está `skipped`; 409 `wrong_channel` si el canal no es
    `whatsapp_link`; 422 `member_without_phone` si el socio no tiene teléfono; 422 `invalid_phone`
    si no es un celular colombiano (confirma el rastro antes de rechazar). Llama
    `members.service.contact_for_notification(session, member_id, "notify", fields={"phone"})` en
    CADA llamada (auditoría `reveal` y `crypto_ops`), marca `sent`, `sent_at` y `sent_by` solo la
    primera vez y confirma antes de responder."""
    aviso = await _locked(session, notification_id)
    if aviso.status == "skipped":
        raise NotificationClosed()
    if aviso.channel != "whatsapp_link":
        raise WrongChannel()
    contacto = await members_service.contact_for_notification(
        session, aviso.member_id, "notify", fields={"phone"}
    )
    if not contacto.phone:
        raise MemberWithoutPhone()
    try:
        url = build_link(contacto.phone, aviso.rendered_body)
    except ValueError:
        # Ya se descifró: se confirma el rastro (`reveal` y `decrypt`) antes de rechazar.
        await session.commit()
        raise InvalidPhone() from None
    if aviso.status != "sent":
        aviso.status = "sent"
        aviso.sent_at = current_clock().now_utc()
        aviso.sent_by = by
        await session.flush()
        await events.emit(
            NotificationSent(
                notification_id=aviso.id, member_id=aviso.member_id, channel="whatsapp_link"
            ),
            session,
        )
    await session.commit()
    return WaLinkOut(url=url)


async def _locked(session: AsyncSession, notification_id: UUID) -> Notification:
    aviso = await session.scalar(
        select(Notification)
        .where(Notification.id == notification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if aviso is None:
        raise NotificationNotFound()
    return aviso


async def skip(
    session: AsyncSession, notification_id: UUID, reason: str, by: UUID
) -> NotificationOut:
    """Omite un aviso `pending` o `failed` con motivo (US-129). 409 `notification_closed` si ya
    está `sent` o `skipped`; emite `NotificationSkipped` sin el motivo."""
    aviso = await _locked(session, notification_id)
    if not can_skip(aviso.status):
        raise NotificationClosed()
    aviso.status = "skipped"
    aviso.skip_reason = reason.strip()
    await session.flush()
    await events.emit(
        NotificationSkipped(
            notification_id=aviso.id,
            member_id=aviso.member_id,
            channel=aviso.channel,  # type: ignore[arg-type]
        ),
        session,
    )
    logger.info("notifications: aviso omitido", extra={"notification_id": str(aviso.id)})
    return await get(session, aviso.id)
