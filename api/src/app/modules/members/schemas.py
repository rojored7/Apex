"""Contrato de socios (S2-B7, US-069; S2-D16, M-4, M-5).

- `MemberCreate` (`extra="forbid"`, `str_strip_whitespace=True`): sin `notes` (M-5) y sin
  `data_consent_at`; el cliente envía `data_consent: bool` y el servidor fija la fecha con su
  reloj (M-4). Enviar cualquiera de los dos campos retirados da 422 con `field`.
- `MemberDetailOut`: los cinco campos sensibles van enmascarados (`str | None`), calculados en
  memoria; nunca el blob ni el claro.
- `MemberRef`: dataclass congelada para otros módulos (nunca el ORM).

S2-B8 (US-070; N-01, N-20, S2-D41):
- `MemberRowOut`: la fila de `GET /members`. Sin ningún campo sensible, ni en claro ni
  enmascarado (N-01): nombres, sexo, estado y `deleted_at`. `membership_status` y `plan_name`
  van `None` hasta el Sprint 3 (US-071).
- `MemberListQuery`: filtros de la lista. `q` de hasta 100 caracteres (nunca se registra),
  `status` (`active`, `inactive` o `deleted`; admin y coach ven a los dados de baja, N-20) y
  `sort` con seis valores (`-` es descendente), `last_name` por defecto.
- `MemberName`: dataclass congelada que devuelve `service.names_for` a otros módulos.

S3-B9b (US-071, US-073; D22, D35): `MembershipFilterStatus`; `MemberListQuery` gana
`membership_status` y `plan_id`; `MemberRowOut.membership_end_date` y
`MemberDetailOut.plan_name`/`membership_end_date` (la membresía que decide el estado; datos
comerciales en claro, no sensibles).

S3-B10 (US-074, US-075; D19, D21, M-3, S3-D46): `RevealIn`/`RevealOut` (`RevealField`),
`EmergencyContactOut` y `MemberPatch` (cerrado, diez campos); `EmergencyContactIn.phone` pasa a
`SafeText`.

Revisión del Sprint 2 (seguridad N-2, Python H2): `first_name`, `last_name` y el `name` y
`relationship` del contacto de emergencia son `SafeText` (NFC, sin `Cc` ni `Cf`, algo visible):
un NUL daba 500 y un U+200B o U+202E pasaban el CHECK y se mostraban en las listas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.core.pagination import MAX_SEARCH_LENGTH
from app.core.validators import EmailAddress, SafeText

DocumentType = Literal["CC", "CE", "TI", "PA"]
Sex = Literal["f", "m", "x"]
MemberStatus = Literal["active", "inactive"]
MemberStatusFilter = Literal["active", "inactive", "deleted"]
# S3-B9b (US-071, D22): estado de membresía por el que se filtra la lista; `none` es "sin
# membresía" (complemento de los otros cinco).
MembershipFilterStatus = Literal[
    "active", "expiring", "expired", "frozen", "pending_payment", "none"
]
MemberSort = Literal[
    "last_name", "-last_name", "first_name", "-first_name", "created_at", "-created_at"
]
DEFAULT_MEMBER_SORT: Final[MemberSort] = "last_name"

NAME_MAX_LENGTH: Final[int] = 100
DOCUMENT_MIN_LENGTH: Final[int] = 3
DOCUMENT_MAX_LENGTH: Final[int] = 30
PHONE_MAX_LENGTH: Final[int] = 30
RELATIONSHIP_MAX_LENGTH: Final[int] = 50
DATA_CONSENT_MISSING: Final[str] = "data_consent_missing"

_ENTRADA = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmergencyContactIn(BaseModel):
    model_config = _ENTRADA

    name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    # S3-D46 (M-3, punto 3): también `SafeText`; antes un NUL o un U+202E pasaban.
    phone: SafeText = Field(min_length=1, max_length=PHONE_MAX_LENGTH)
    relationship: SafeText | None = Field(default=None, max_length=RELATIONSHIP_MAX_LENGTH)


class MemberCreate(BaseModel):
    model_config = _ENTRADA

    first_name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    last_name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    document_type: DocumentType = "CC"
    # Revisión de seguridad de S3-B10 (LOW-1): `SafeText` también en documento y teléfono; un
    # NUL o un U+202E se guardaban cifrados y salían tal cual al revelar.
    document: SafeText = Field(min_length=DOCUMENT_MIN_LENGTH, max_length=DOCUMENT_MAX_LENGTH)
    phone: SafeText | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    email: EmailAddress | None = None
    birth_date: date | None = None
    sex: Sex | None = None
    emergency_contact: EmergencyContactIn | None = None
    # Autorización legal (M-4): solo un `true` JSON literal (revisión S2-B7, LOW-5).
    data_consent: bool = Field(default=False, strict=True)


class MemberDetailOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    sex: Sex | None
    status: MemberStatus
    document_type: DocumentType
    document: str | None
    phone: str | None
    email: str | None
    birth_date: str | None
    emergency_contact: str | None
    data_consent_at: datetime | None
    data_consent_version: str | None
    deleted_at: datetime | None
    membership_status: str | None = None
    # S3-B9b (US-073, D22): la membresía que decide el estado (`memberships.status_for`).
    plan_name: str | None = None
    membership_end_date: date | None = None
    created_at: datetime
    updated_at: datetime
    warnings: list[str]


@dataclass(frozen=True)
class MemberRef:
    """Lo que otros módulos saben de un socio (contrato de `service.get_ref`)."""

    id: UUID
    first_name: str
    last_name: str
    status: str
    is_deleted: bool


class MemberRowOut(BaseModel):
    """Fila de la lista de socios: nada sensible, ni enmascarado (N-01)."""

    id: UUID
    first_name: str
    last_name: str
    sex: Sex | None
    status: MemberStatus
    deleted_at: datetime | None
    membership_status: str | None = None
    plan_name: str | None = None
    membership_end_date: date | None = None  # S3-B9b (D22, D35): "Vence" de la lista


class MemberListQuery(BaseModel):
    """Filtros de `service.list`; el router los arma desde la query string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    q: str | None = Field(default=None, max_length=MAX_SEARCH_LENGTH)
    status: MemberStatusFilter | None = None
    sort: MemberSort = DEFAULT_MEMBER_SORT
    # S3-B9b (US-071, D22): estado de la membresía que decide y su plan.
    membership_status: MembershipFilterStatus | None = None
    plan_id: UUID | None = None


@dataclass(frozen=True)
class MemberName:
    """Nombre de un socio para otros módulos (incluye dados de baja; nunca el ORM)."""

    id: UUID
    first_name: str
    last_name: str
    sex: str | None


# S3-B10 (US-074, US-075; D19, D21, M-3, S3-D46) ----------------------------------------

RevealField = Literal["document", "phone", "email", "birth_date", "emergency_contact"]
"""Los cinco campos cifrados que se pueden revelar (D19); cualquier otro da 422 `field`."""

PATCH_NOT_NULL: Final[tuple[str, ...]] = (
    "first_name",
    "last_name",
    "document",
    "document_type",
    "data_consent",
)
"""Campos de `MemberPatch` que se pueden omitir pero no enviar como `null` (422 con `field`)."""


class EmergencyContactOut(BaseModel):
    """El contacto de emergencia en claro: solo en la respuesta de `reveal`."""

    name: str
    phone: str
    relationship: str | None = None


class RevealIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: RevealField


class RevealOut(BaseModel):
    """El valor en claro de UN campo (`birth_date` como `AAAA-MM-DD`; vacío, `None`). Viaja solo
    en esta respuesta, con `Cache-Control: no-store`; nunca se guarda ni se registra."""

    field: RevealField
    value: str | EmergencyContactOut | None


class MemberPatch(BaseModel):
    """`PATCH /members/{member_id}` cerrado (S3-D46): exactamente estos diez campos, todos
    opcionales; `model_fields_set` distingue "no enviado" de `null`. `document` y
    `document_type` son de admin (por presencia, M-3). `status`, `deleted_at` y
    `data_consent_at` nunca entran (`extra="forbid"`). `data_consent` solo `true` (un `false`
    lo rechaza el service con 422)."""

    model_config = _ENTRADA

    first_name: SafeText | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    last_name: SafeText | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    sex: Sex | None = None
    birth_date: date | None = None
    phone: SafeText | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
    email: EmailAddress | None = None
    emergency_contact: EmergencyContactIn | None = None
    document: SafeText | None = Field(
        default=None, min_length=DOCUMENT_MIN_LENGTH, max_length=DOCUMENT_MAX_LENGTH
    )
    document_type: DocumentType | None = None
    data_consent: StrictBool | None = None

    @field_validator(*PATCH_NOT_NULL, mode="before")
    @classmethod
    def _sin_null(cls, valor: object) -> object:
        """`null` en un nombre, el documento, su tipo o la autorización da 422 con `field`."""
        if valor is None:
            raise ValueError("Este campo no admite null.")
        return valor
