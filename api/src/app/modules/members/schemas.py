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

Revisión del Sprint 2 (seguridad N-2, Python H2): `first_name`, `last_name` y el `name` y
`relationship` del contacto de emergencia son `SafeText` (NFC, sin `Cc` ni `Cf`, algo visible):
un NUL daba 500 y un U+200B o U+202E pasaban el CHECK y se mostraban en las listas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import MAX_SEARCH_LENGTH
from app.core.validators import EmailAddress, SafeText

DocumentType = Literal["CC", "CE", "TI", "PA"]
Sex = Literal["f", "m", "x"]
MemberStatus = Literal["active", "inactive"]
MemberStatusFilter = Literal["active", "inactive", "deleted"]
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
    phone: str = Field(min_length=1, max_length=PHONE_MAX_LENGTH)
    relationship: SafeText | None = Field(default=None, max_length=RELATIONSHIP_MAX_LENGTH)


class MemberCreate(BaseModel):
    model_config = _ENTRADA

    first_name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    last_name: SafeText = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    document_type: DocumentType = "CC"
    document: str = Field(min_length=DOCUMENT_MIN_LENGTH, max_length=DOCUMENT_MAX_LENGTH)
    phone: str | None = Field(default=None, max_length=PHONE_MAX_LENGTH)
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


class MemberListQuery(BaseModel):
    """Filtros de `service.list`; el router los arma desde la query string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    q: str | None = Field(default=None, max_length=MAX_SEARCH_LENGTH)
    status: MemberStatusFilter | None = None
    sort: MemberSort = DEFAULT_MEMBER_SORT


@dataclass(frozen=True)
class MemberName:
    """Nombre de un socio para otros módulos (incluye dados de baja; nunca el ORM)."""

    id: UUID
    first_name: str
    last_name: str
    sex: str | None
