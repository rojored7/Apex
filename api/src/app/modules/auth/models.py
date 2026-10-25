"""Tablas del esquema `auth` (US-041 T4): `users`, `refresh_tokens`, `one_time_tokens`.

- `User` se audita con `password_hash` redactado (`"***"`) y `last_login_at` fuera del diff
  (US-042). `member_id` es un UUID sin FK entre esquemas (S7); la base exige `member_id` para
  el rol `member`. El correo de login va en claro (P5).
- `User` (S2-B2, `0005b_auth_security`): `must_change_password` (M-8), `failed_login_count`
  con CHECK no negativo (L-10, S2-D10) y `tokens_valid_after` (H-3). El contador y el corte
  quedan fuera del diff de auditoría (los cambia un `UPDATE` directo; S2-D49).
- `RefreshToken` no se audita: rota cada 15 minutos; `replaced_by_id` detecta reuso (N-13) y
  `family_started_at` fija el tope absoluto de la familia (L-4); el service lo escribe siempre
  con el reloj de la app y la rotación lo hereda.
- `OneTimeToken` (activación y restablecimiento, US-047/048) sí se audita.
Los usuarios nunca se borran físicamente (RN-14; `test_no_physical_delete.py`, S3-B10).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin, SoftDeleteMixin
from app.core.security import Role

ROLES: tuple[str, ...] = ("admin", "coach", "member")
OTT_PURPOSES: tuple[str, ...] = ("activate", "reset")


class User(CommonColumnsMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'coach', 'member')", name="role"),
        CheckConstraint("role <> 'member' OR member_id IS NOT NULL", name="member_id_for_member"),
        CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
        Index(
            "uq_users_email_alive",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": "auth"},
    )
    __audited__: ClassVar[bool] = True
    __audit_redact__: ClassVar[frozenset[str]] = frozenset({"password_hash"})
    # `last_login_at`, `failed_login_count` y `tokens_valid_after` fuera del diff (S2-D49, L-10).
    __audit_exclude__: ClassVar[frozenset[str]] = frozenset(
        {"last_login_at", "failed_login_count", "tokens_valid_after"}
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[Role] = mapped_column(Text, nullable=False)  # M9: el Literal de `core.security`
    member_id: Mapped[UUID | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    tokens_valid_after: Mapped[datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:  # sin password_hash
        return f"User(id={self.id}, role={self.role!r})"


class RefreshToken(CommonColumnsMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"), {"schema": "auth"})

    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("auth.refresh_tokens.id"), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    family_started_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("now()")
    )


class OneTimeToken(CommonColumnsMixin, Base):
    __tablename__ = "one_time_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('activate', 'reset')", name="purpose"),
        Index(
            "ix_ott_user_purpose_open",
            "user_id",
            "purpose",
            postgresql_where=text("used_at IS NULL"),
        ),
        {"schema": "auth"},
    )
    __audited__: ClassVar[bool] = True
    __audit_redact__: ClassVar[frozenset[str]] = frozenset({"token_hash"})

    user_id: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
