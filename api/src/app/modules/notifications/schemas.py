"""Contrato de plantillas y reglas de aviso (S5-B6, US-120 y US-121; S5-D24, S5-D25).

- `TemplateCreate` / `TemplatePatch` (`extra="forbid"`): `name` hasta 80, `subject` hasta 150 y
  `body` hasta 2.000 caracteres. Las variables las valida el service (`field` = `subject`/`body`).
- `RuleCreate` / `RulePatch` (`extra="forbid"`): `trigger` y `channel` cerrados, `offset_days`
  `StrictInt` de -3650 a 3650 (el signo según el disparador lo valida `rules.validate_rule`).
- `PreviewIn` / `PreviewOut`: vista previa con un contexto de ejemplo; mismos tipos y topes que
  `TemplateCreate` (S5-D216).
- `RuleFilters`: filtros ya validados de la lista de reglas.
- `SeedResult`: lo que creó `seed_defaults` (en 0 la segunda vez).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.core.validators import SafeMultilineText, SafeText

Trigger = Literal["membership_expiring", "membership_expired"]
Channel = Literal["email", "whatsapp_link"]

NAME_MAX_LENGTH: Final = 80
SUBJECT_MAX_LENGTH: Final = 150
BODY_MAX_LENGTH: Final = 2_000
OFFSET_MIN: Final = -3_650
OFFSET_MAX: Final = 3_650


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    subject: SafeText = Field(min_length=1, max_length=SUBJECT_MAX_LENGTH)
    body: SafeMultilineText = Field(min_length=1, max_length=BODY_MAX_LENGTH)


class TemplatePatch(BaseModel):
    """Todo opcional; lo no enviado no cambia (`model_fields_set`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SafeText | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    subject: SafeText | None = Field(default=None, min_length=1, max_length=SUBJECT_MAX_LENGTH)
    body: SafeMultilineText | None = Field(default=None, min_length=1, max_length=BODY_MAX_LENGTH)


class TemplateOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    subject: str
    body: str
    created_at: datetime
    updated_at: datetime


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: SafeText = Field(min_length=1, max_length=SUBJECT_MAX_LENGTH)
    body: SafeMultilineText = Field(min_length=1, max_length=BODY_MAX_LENGTH)


class PreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    body: str


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    trigger: Trigger
    offset_days: StrictInt = Field(ge=OFFSET_MIN, le=OFFSET_MAX)
    channel: Channel
    template_id: UUID
    is_active: StrictBool = True


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SafeText | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    trigger: Trigger | None = None
    offset_days: StrictInt | None = Field(default=None, ge=OFFSET_MIN, le=OFFSET_MAX)
    channel: Channel | None = None
    template_id: UUID | None = None
    is_active: StrictBool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    trigger: Trigger
    offset_days: int
    channel: Channel
    template_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RuleFilters:
    q: str | None = None
    is_active: bool | None = None
    channel: Channel | None = None
    trigger: Trigger | None = None


@dataclass(frozen=True)
class SeedResult:
    templates_created: int
    rules_created: int


# Avisos (S5-B7, US-124, US-127 a US-130) --------------------------------------------------------

Status = Literal["pending", "sent", "failed", "skipped"]
SKIP_REASON_MIN: Final = 3
SKIP_REASON_MAX: Final = 500


class SkipIn(BaseModel):
    """Cuerpo de `POST /notifications/{id}/skip`: el motivo, de 3 a 500 caracteres visibles."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: SafeText = Field(min_length=SKIP_REASON_MIN, max_length=SKIP_REASON_MAX)


class WaLinkOut(BaseModel):
    """`POST /notifications/{id}/wa-link`: el enlace `https://wa.me/57<digitos>?text=...`."""

    model_config = ConfigDict(extra="forbid")

    url: str


class NotificationOut(BaseModel):
    """Un aviso tal como lo ven admin y coach. Nunca lleva teléfono ni correo."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    rule_id: UUID
    member_id: UUID
    member_name: str
    membership_id: UUID
    target_date: date
    channel: Channel
    status: Status
    rendered_subject: str
    rendered_body: str
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    sent_by: UUID | None
    skip_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NotificationFilters:
    """Filtros ya validados de `GET /notifications` (S5-D92). `from_date` y `to_date` filtran por
    `target_date`, ambos extremos incluidos."""

    q: str | None = None
    status: Status | None = None
    channel: Channel | None = None
    rule_id: UUID | None = None
    from_date: date | None = None
    to_date: date | None = None


@dataclass(frozen=True)
class GenerateResult:
    """Lo que hizo `generate_today`. `generados` son avisos nuevos (filas insertadas);
    `ya_renovaron` cuenta socios distintos omitidos por N-35 (vencida con una vigente);
    `sin_consentimiento`
    cuenta socios distintos sin canal alguno (sin consentimiento o inexistentes); `sin_reglas` es
    verdadero
    cuando no hay ninguna regla activa."""

    generados: int
    ya_renovaron: int
    sin_consentimiento: int
    sin_reglas: bool
    omitidos_por_plantilla: int = 0


@dataclass(frozen=True)
class SendResult:
    """Resultado de una pasada de `sending.send_pending` (B8)."""

    enviados: int
    fallidos: int
    omitidos: int
