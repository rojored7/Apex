"""Tablas `notifications.notification_templates` y `notification_rules` (S5-B6, S5-D24).

Migraciones `0017_notification_templates` y `0018_notification_rules`. Ambas con
`__audited__ = True`; no tienen sujeto de socio (son configuración). Sin borrado: las reglas se
desactivan y las plantillas no se borran (RN-14).
"""

from __future__ import annotations

from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

TRIGGERS: Final[tuple[str, ...]] = ("membership_expiring", "membership_expired")
CHANNELS: Final[tuple[str, ...]] = ("email", "whatsapp_link")
TEMPLATE_NAME_UNIQUE: Final = "uq_notification_templates_name"
RULE_ACTIVE_KEY_INDEX: Final = "uq_notification_rules_active_key"


class NotificationTemplate(CommonColumnsMixin, Base):
    __tablename__ = "notification_templates"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("btrim(subject) <> ''", name="subject_not_blank"),
        CheckConstraint("btrim(body) <> ''", name="body_not_blank"),
        UniqueConstraint("name", name=TEMPLATE_NAME_UNIQUE),
        {"schema": "notifications"},
    )
    __audited__: ClassVar[bool] = True

    name: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class NotificationRule(CommonColumnsMixin, Base):
    __tablename__ = "notification_rules"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("trigger IN ('membership_expiring', 'membership_expired')", name="trigger"),
        CheckConstraint("channel IN ('email', 'whatsapp_link')", name="channel"),
        CheckConstraint(
            "(trigger = 'membership_expiring' AND offset_days <= 0) "
            "OR (trigger = 'membership_expired' AND offset_days >= 1)",
            name="offset_days_sign",
        ),
        Index(
            RULE_ACTIVE_KEY_INDEX,
            "trigger",
            "offset_days",
            "channel",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        {"schema": "notifications"},
    )
    __audited__: ClassVar[bool] = True

    name: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.notification_templates.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
