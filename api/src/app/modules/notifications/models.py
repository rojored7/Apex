"""Tablas `notifications.notification_templates`, `notification_rules` y `notifications`
(S5-B6 y S5-B7, S5-D24).

Migraciones `0017_notification_templates`, `0018_notification_rules` y `0019_notifications`. Todas
con `__audited__ = True`; plantillas y reglas no tienen sujeto de socio (son configuración) y
`Notification` lleva `__audit_subject__ = "member_id"` (G-05). Sin borrado: las reglas se
desactivan,
las plantillas no se borran y los avisos se envían u omiten (RN-14).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar, Final
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
STATUSES: Final[tuple[str, ...]] = ("pending", "sent", "failed", "skipped")
ERROR_CODES: Final[tuple[str, ...]] = ("timeout", "auth", "refused", "invalid_recipient", "unknown")
NOTIFICATION_KEY: Final = "uq_notifications_rule_membership_target"


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


class Notification(CommonColumnsMixin, Base):
    """Un aviso de una regla para una membresía en una fecha objetivo (RN-17, S5-D24)."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'whatsapp_link')", name="channel"),
        CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts"),
        CheckConstraint("status <> 'skipped' OR skip_reason IS NOT NULL", name="skip_reason"),
        CheckConstraint(
            "last_error IS NULL OR last_error IN "
            "('timeout', 'auth', 'refused', 'invalid_recipient', 'unknown')",
            name="last_error",
        ),
        UniqueConstraint("rule_id", "membership_id", "target_date", name=NOTIFICATION_KEY),
        Index("ix_notifications_status_target_date", "status", "target_date"),
        Index("ix_notifications_member_target_date", "member_id", text("target_date DESC")),
        {"schema": "notifications"},
    )
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"

    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.notification_rules.id", ondelete="RESTRICT"), nullable=False
    )
    member_id: Mapped[UUID] = mapped_column(nullable=False)
    membership_id: Mapped[UUID] = mapped_column(nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_subject: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_body: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_by: Mapped[UUID | None] = mapped_column(nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
