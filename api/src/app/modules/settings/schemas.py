"""Schemas de settings (US-054, US-055, US-057, US-058; blueprint del Sprint 2, B1).

Contrato (N-18, S2-D15, D5):
- `SectionValue`: `ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)`.
- `GymSettings`: `name` (1 a 80, sin default en el modelo; vacío o ausente da 422),
  `nit: str | None` (`NIT_PATTERN`: dígitos y un dígito de verificación opcional, hasta 15),
  `address` (hasta 120), `city` (hasta 60), `phone` (hasta 20), `whatsapp` (hasta 20),
  `email: EmailAddress | None`; los opcionales son `None` por defecto.
- `PrivacySettings`: `policy_version` (1 a 20), `policy_text` (1 a 20.000),
  `retention_years` estricto 1 a 20 (5), `consent_required_from: date | None = None`.
  `PrivacyView` (solo salida): igual, con `policy_version` y `policy_text` que admiten `None`.
- `MembershipsSettings`: cuatro `StrictInt`: `expiring_days` 1 a 30 (7),
  `max_freeze_days_per_membership` 0 a 180 (30), `max_freezes_per_membership` 0 a 12 (2),
  `max_retroactive_days` 0 a 30 (7).
- `SECTION_REGISTRY`: exactamente las tres de `ENABLED_SECTIONS` (esquemas de escritura);
  `SECTION_VIEWS`: los de lectura (`privacy` sin publicar se lee con `PrivacyView`).
- `SECTION_DEFAULTS`: `gym` con `name = "APEX"` y el resto `None`; `privacy` con
  `policy_version`/`policy_text`/`consent_required_from` en `None` y `retention_years = 5`;
  `memberships` con 7, 30, 2 y 7. El service entrega copias (`defaults_for`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.core.validators import EmailAddress


class SectionKey(StrEnum):
    gym = "gym"
    hours = "hours"
    payment_methods = "payment_methods"
    channels = "channels"
    classes = "classes"
    memberships = "memberships"
    tv = "tv"
    privacy = "privacy"


# S2-D15: `payment_methods` (US-056) queda fuera del Sprint 2 y responde 404.
ENABLED_SECTIONS: frozenset[SectionKey] = frozenset(
    {SectionKey.gym, SectionKey.privacy, SectionKey.memberships}
)

NIT_PATTERN: Final[str] = r"^\d+(-\d)?$"
RETENCION_POR_DEFECTO: Final[int] = 5

PolicyVersion = Annotated[str, Field(min_length=1, max_length=20)]
PolicyText = Annotated[str, Field(min_length=1, max_length=20_000)]
RetentionYears = Annotated[StrictInt, Field(ge=1, le=20)]


class SectionValue(BaseModel):
    """Base de todo esquema de sección: sin campos extra e inmutable (Q12, US-054 T5)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GymSettings(SectionValue):
    """Datos del gimnasio (US-055, N-18). `name` sin default: el `"APEX"` vive en los defaults."""

    name: str = Field(min_length=1, max_length=80)
    nit: str | None = Field(default=None, max_length=15, pattern=NIT_PATTERN)
    address: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=20)
    whatsapp: str | None = Field(default=None, max_length=20)
    email: EmailAddress | None = None


class PrivacySettings(SectionValue):
    """Política de privacidad (US-057, N-18): publicar exige versión y texto."""

    policy_version: PolicyVersion
    policy_text: PolicyText
    retention_years: RetentionYears = RETENCION_POR_DEFECTO
    consent_required_from: date | None = None


class PrivacyView(SectionValue):
    """Salida de `privacy`: la política nunca publicada tiene versión y texto `None`."""

    policy_version: PolicyVersion | None = None
    policy_text: PolicyText | None = None
    retention_years: RetentionYears = RETENCION_POR_DEFECTO
    consent_required_from: date | None = None


class MembershipsSettings(SectionValue):
    """Parámetros de membresías (US-058, N-18). Enteros estrictos: `"7"`, `7.5`, `7.0` dan 422."""

    expiring_days: StrictInt = Field(default=7, ge=1, le=30)
    max_freeze_days_per_membership: StrictInt = Field(default=30, ge=0, le=180)
    max_freezes_per_membership: StrictInt = Field(default=2, ge=0, le=12)
    max_retroactive_days: StrictInt = Field(default=7, ge=0, le=30)


@dataclass(frozen=True)
class MembershipsPolicy:
    """Contrato que `memberships.service` importa desde `settings.schemas` (S2-D45)."""

    expiring_days: int
    max_freeze_days_per_membership: int
    max_freezes_per_membership: int
    max_retroactive_days: int


# Esquemas de escritura de las tres secciones habilitadas (S2-D15).
SECTION_REGISTRY: dict[SectionKey, type[SectionValue]] = {
    SectionKey.gym: GymSettings,
    SectionKey.privacy: PrivacySettings,
    SectionKey.memberships: MembershipsSettings,
}

# Esquemas de lectura: `privacy` sin publicar no valida contra `PrivacySettings`.
SECTION_VIEWS: dict[SectionKey, type[SectionValue]] = {
    **SECTION_REGISTRY,
    SectionKey.privacy: PrivacyView,
}

# Valores de una sección nunca guardada (sin filas sembradas). Solo se leen por copia.
SECTION_DEFAULTS: dict[SectionKey, dict[str, Any]] = {
    SectionKey.gym: {
        "name": "APEX",
        "nit": None,
        "address": None,
        "city": None,
        "phone": None,
        "whatsapp": None,
        "email": None,
    },
    SectionKey.privacy: {
        "policy_version": None,
        "policy_text": None,
        "retention_years": RETENCION_POR_DEFECTO,
        "consent_required_from": None,
    },
    SectionKey.memberships: {
        "expiring_days": 7,
        "max_freeze_days_per_membership": 30,
        "max_freezes_per_membership": 2,
        "max_retroactive_days": 7,
    },
}


# Entradas y salidas del API -------------------------------------------------------------


class _SectionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: SectionKey
    version: int = Field(ge=0)
    updated_at: datetime | None
    updated_by: UUID | None


class SectionOut(_SectionMeta):
    """Sección genérica: fila guardada o defaults con `version = 0` y `updated_* = None`."""

    value: dict[str, Any]


class GymSectionOut(_SectionMeta):
    value: GymSettings


class PrivacySectionOut(_SectionMeta):
    value: PrivacyView


class MembershipsSectionOut(_SectionMeta):
    value: MembershipsSettings


class SectionPatchIn(BaseModel):
    """`PATCH` reemplaza la sección completa con la versión que se leyó (N-17, S2-D15)."""

    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]
    version: int = Field(ge=0)


class GymPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: GymSettings
    version: int = Field(ge=0)


class PrivacyPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: PrivacySettings
    version: int = Field(ge=0)


class MembershipsPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: MembershipsSettings
    version: int = Field(ge=0)
