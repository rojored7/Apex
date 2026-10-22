"""Tabla `settings.settings_sections` (US-054 T2; migración `0005_settings`).

Una fila por sección guardada al menos una vez: `key` (una de las 8 claves del `CHECK
key_valid`), `value` (JSONB validado por el esquema de la sección), `version` (bloqueo
optimista, N-17; 0 por defecto y 1 tras el primer guardado) y `updated_by`. Sin filas
sembradas: los valores por defecto viven en `schemas.SECTION_DEFAULTS`. Se audita completa
con el hook de US-016 (`insert` en el primer guardado y `update` desde el segundo).
Nadie fuera de `settings` importa este archivo (`test_no_cross_models.py`).
"""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Integer, Text, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CommonColumnsMixin

SECTION_KEYS: tuple[str, ...] = (
    "gym",
    "hours",
    "payment_methods",
    "channels",
    "classes",
    "memberships",
    "tv",
    "privacy",
)


class SettingsSection(CommonColumnsMixin, Base):
    __tablename__ = "settings_sections"
    __table_args__ = (
        CheckConstraint(
            "key IN ('gym', 'hours', 'payment_methods', 'channels', 'classes', "
            "'memberships', 'tv', 'privacy')",
            name="key_valid",
        ),
        CheckConstraint("version >= 0", name="version_non_negative"),
        Index("uq_settings_sections_key", "key", unique=True),
        {"schema": "settings"},
    )
    __audited__: ClassVar[bool] = True

    key: Mapped[str] = mapped_column(Text, nullable=False)
    # En cada guardado se asigna un dict nuevo (regla transversal 5): mutarlo en sitio no
    # dejaría historial y el hook no auditaría el cambio.
    value: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_by: Mapped[UUID | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:  # sin el valor
        return f"SettingsSection(key={self.key!r}, version={self.version})"
