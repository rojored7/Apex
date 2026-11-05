"""Fábrica de `notifications.notification_templates` y `notification_rules` (S5-B6; US-120, US-121).

- `make_template(session, **cambios)`: inserta una plantilla "Vence pronto" bajo
  `actor_scope(SYSTEM_USER_ID)`; `flush` y commit del savepoint.
- `make_rule(session, template=None, **cambios)`: regla activa `membership_expiring` / -3 /
  `whatsapp_link`; crea una plantilla si no se pasa `template`.
- `DEFAULT_TEMPLATES` y `DEFAULT_RULES`: el ORÁCULO de la siembra (S5-D25): dos plantillas y cinco
  reglas, todas `whatsapp_link`. `seed_defaults_db(session)` las inserta directo con el ORM
  (sin pasar por `notifications.service`) para que otras pruebas partan de ellas.
- `make_notification(session, rule=None, **cambios)` (S5-B7): inserta un aviso `pending` por ORM
  bajo `actor_scope(SYSTEM_USER_ID)` (la auditoría lo ve), con `flush`, commit del savepoint y
  `expunge`. Sin `rule` crea una regla; `member_id` y `membership_id` por defecto son ids sueltos
  (la tabla no tiene FK hacia otros esquemas); `target_date` por defecto es el "hoy" de Bogotá del
  reloj. Si el estado es `skipped` pone un motivo y si es `sent` pone `sent_at`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.modules.notifications.models import Notification, NotificationRule, NotificationTemplate

SOON: Final = "Vence pronto"
EXPIRED: Final = "Venció"

DEFAULT_TEMPLATES: Final[dict[str, tuple[str, str]]] = {
    SOON: (
        "Tu membresía vence pronto",
        "Hola {nombre}, tu plan {plan} vence el {vence} (en {dias} días). Te esperamos.",
    ),
    EXPIRED: (
        "Tu membresía venció",
        "Hola {nombre}, tu plan {plan} venció el {vence}. Renuévalo cuando quieras.",
    ),
}


@dataclass(frozen=True)
class DefaultRule:
    name: str
    trigger: str
    offset_days: int
    template: str


DEFAULT_RULES: Final[tuple[DefaultRule, ...]] = (
    DefaultRule("Vence en 3 días", "membership_expiring", -3, SOON),
    DefaultRule("Vence hoy", "membership_expiring", 0, SOON),
    DefaultRule("Venció hace 1 día", "membership_expired", 1, EXPIRED),
    DefaultRule("Venció hace 7 días", "membership_expired", 7, EXPIRED),
    DefaultRule("Venció hace 15 días", "membership_expired", 15, EXPIRED),
)
CHANNEL: Final = "whatsapp_link"


async def make_template(session: AsyncSession, **cambios: Any) -> NotificationTemplate:
    valores: dict[str, Any] = {
        "name": SOON,
        "subject": DEFAULT_TEMPLATES[SOON][0],
        "body": DEFAULT_TEMPLATES[SOON][1],
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    plantilla = NotificationTemplate(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(plantilla)
        await session.flush()
        await session.commit()
        session.expunge(plantilla)  # S5-B6: un rollback posterior no la expira (async no recarga)
    return plantilla


async def make_rule(
    session: AsyncSession, template: NotificationTemplate | None = None, **cambios: Any
) -> NotificationRule:
    plantilla = template or (None if "template_id" in cambios else await make_template(session))
    valores: dict[str, Any] = {
        "name": "Regla de prueba",
        "trigger": "membership_expiring",
        "offset_days": -3,
        "channel": CHANNEL,
        "template_id": plantilla.id if plantilla else None,
        "is_active": True,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    regla = NotificationRule(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(regla)
        await session.flush()
        await session.commit()
        session.expunge(regla)
    return regla


async def seed_defaults_db(
    session: AsyncSession,
) -> tuple[dict[str, NotificationTemplate], list[NotificationRule]]:
    """Las dos plantillas y las cinco reglas por defecto, insertadas directo con el ORM."""
    plantillas = {
        nombre: await make_template(session, name=nombre, subject=asunto, body=cuerpo)
        for nombre, (asunto, cuerpo) in DEFAULT_TEMPLATES.items()
    }
    reglas = [
        await make_rule(
            session,
            plantillas[d.template],
            name=d.name,
            trigger=d.trigger,
            offset_days=d.offset_days,
        )
        for d in DEFAULT_RULES
    ]
    return plantillas, reglas


async def make_notification(
    session: AsyncSession, rule: NotificationRule | None = None, **cambios: Any
) -> Notification:
    regla = rule or await make_rule(session)
    valores: dict[str, Any] = {
        "rule_id": regla.id,
        "member_id": uuid4(),
        "membership_id": uuid4(),
        "target_date": current_clock().today_bogota(),
        "channel": regla.channel,
        "status": "pending",
        "rendered_subject": "Tu membresía vence pronto",
        "rendered_body": "Hola Lucía, tu plan Mensual vence el 24 oct 2026 (en 3 días).",
        "attempts": 0,
        "created_by": SYSTEM_USER_ID,
    }
    valores.update(cambios)
    if valores["status"] == "skipped":
        valores.setdefault("skip_reason", "Motivo de prueba")
    if valores["status"] == "sent":
        valores.setdefault("sent_at", current_clock().now_utc())
    aviso = Notification(**valores)
    with actor_scope(SYSTEM_USER_ID):
        session.add(aviso)
        await session.flush()
        await session.commit()
        session.expunge(aviso)
    return aviso
