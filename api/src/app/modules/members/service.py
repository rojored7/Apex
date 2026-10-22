"""Caso de uso de socios (S2-B7, US-069; M-4, M-5, L-1, L-3).

Puras:
- `validate_member_input(data, today)`: nombres no vacíos, `sex` en `f`/`m`/`x` o nulo,
  `birth_date <= today` (`today` es `today_bogota()`), documento o correo que no se normalicen
  a vacío y teléfono con al menos `PHONE_MIN_DIGITS` dígitos tras normalizar (L-3: `"+57"` se
  normaliza a `"57"`). Lanza `MemberValidationError` con `field` y sin repetir el valor.
- `compute_warnings(data)`: `["data_consent_missing"]` sin autorización, `[]` con ella.
- `mask(field, value, *, document_type=None)`: enmascarado en memoria del valor de entrada
  (`CC •••• 0304`, `••• ••• 4567`, `l•••@•••.co`, `••/••/1991`, `"Registrado"`); `None` da
  `None`. Nunca opera sobre el blob.

Con sesión:
- `create(session, data)`: valida, pre-chequea el documento por índice ciego, arma el `Member`
  con `Secret.from_plain`, `data_consent_at = clock.now_utc()` si `data_consent` (M-4) y
  `data_consent_version = None`; la carrera la decide `uq_members_document_idx_alive` dentro de
  `begin_nested()`; emite `MemberCreated`; responde enmascarado sin descifrar nada. El actor sale
  de `current_actor`.
- Contratos para otros módulos: `get_ref`, `ensure_exists`, `id_by_document`, `count`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.normalize import IndexKind, normalize_for_index
from app.core.crypto.secret import PlainValue, Secret
from app.core.events import DomainEvent
from app.modules.members.exceptions import (
    MemberDocumentDuplicated,
    MemberNotFound,
    MemberValidationError,
)
from app.modules.members.models import SEXES, Member
from app.modules.members.schemas import (
    DATA_CONSENT_MISSING,
    MemberCreate,
    MemberDetailOut,
    MemberRef,
)

logger = logging.getLogger("app.members")

MaskField = Literal["document", "phone", "email", "birth_date", "emergency_contact"]
MaskValue = str | date | Mapping[str, Any] | None

DOCUMENT_DATA_CLASS: Final = "member.document"
DOCUMENT_ALIVE_INDEX: Final = "uq_members_document_idx_alive"
PHONE_MIN_DIGITS: Final = 7  # L-3: "+57" queda en "57"; un fijo local tiene 7 dígitos
MASK_TAIL: Final = 4
DOCUMENT_MIN_MASKED: Final = 6  # al menos 2 caracteres ocultos además de la cola
DOTS: Final = "•••"
EMERGENCY_CONTACT_MASK: Final = "Registrado"

_MENSAJES: Final[Mapping[str, str]] = {
    "first_name": "El nombre es obligatorio.",
    "last_name": "El apellido es obligatorio.",
    "sex": "El sexo debe ser f, m o x.",
    "birth_date": "La fecha de nacimiento no puede ser futura.",
    "document": "El documento no tiene caracteres válidos.",
    "phone": "El teléfono no tiene suficientes dígitos.",
    "email": "El correo no es válido.",
}


@dataclass(frozen=True, kw_only=True)
class MemberCreated(DomainEvent):
    member_id: UUID


# Reglas puras --------------------------------------------------------------------------


def _invalido(campo: str) -> MemberValidationError:
    """422 con `field`; el mensaje nunca repite el valor recibido."""
    return MemberValidationError(message=_MENSAJES[campo], field=campo)


def _normalizado(valor: str, kind: IndexKind) -> str:
    """Forma del índice ciego, o `""` si el valor se normaliza a vacío (L-3)."""
    try:
        return normalize_for_index(valor, kind)
    except CryptoError:
        return ""


def validate_member_input(data: MemberCreate, today: date) -> None:
    for campo in ("first_name", "last_name"):
        if not str(getattr(data, campo) or "").strip():
            raise _invalido(campo)
    if data.sex is not None and data.sex not in SEXES:
        raise _invalido("sex")
    if data.birth_date is not None and data.birth_date > today:
        raise _invalido("birth_date")
    if not _normalizado(data.document, "generic"):
        raise _invalido("document")
    if data.phone is not None and len(_normalizado(data.phone, "phone")) < PHONE_MIN_DIGITS:
        raise _invalido("phone")
    if data.email is not None and not _normalizado(data.email, "email"):
        raise _invalido("email")


def compute_warnings(data: MemberCreate) -> list[str]:
    return [] if data.data_consent else [DATA_CONSENT_MISSING]


def _mask_document(value: str, document_type: str | None) -> str:
    """Los 4 últimos del normalizado; un documento de menos de `DOCUMENT_MIN_MASKED` caracteres
    va sin cola para no mostrarlo entero (revisión S2-B7, LOW-2)."""
    normalizado = _normalizado(value, "generic").upper()
    prefijo = f"{document_type or 'CC'} •{DOTS}"
    if len(normalizado) < DOCUMENT_MIN_MASKED:
        return prefijo
    return f"{prefijo} {normalizado[-MASK_TAIL:]}"


def _mask_phone(value: str) -> str:
    digitos = "".join(c for c in value if c in "0123456789")
    return f"{DOTS} {DOTS} {digitos[-MASK_TAIL:]}"


def _mask_email(value: str) -> str:
    local, _, dominio = value.strip().lower().rpartition("@")
    inicial = local[:1] or "•"
    etiqueta = dominio.rsplit(".", 1)[-1] if "." in dominio else DOTS
    return f"{inicial}{DOTS}@{DOTS}.{etiqueta}"


def mask(field: MaskField, value: MaskValue, *, document_type: str | None = None) -> str | None:
    """Enmascarado en memoria del valor de entrada; nunca opera sobre el blob."""
    if value is None:
        return None
    if field == "emergency_contact":
        return EMERGENCY_CONTACT_MASK
    if field == "birth_date":
        anio = value.year if isinstance(value, date) else date.fromisoformat(str(value)).year
        return f"••/••/{anio:04d}"
    if not isinstance(value, str):
        raise TypeError(f"{field} se enmascara desde texto")
    if field == "document":
        return _mask_document(value, document_type)
    if field == "phone":
        return _mask_phone(value)
    return _mask_email(value)


# Alta ---------------------------------------------------------------------------------


def _secreto(valor: PlainValue | None) -> Secret | None:
    return None if valor is None else Secret.from_plain(valor)


def _contacto(data: MemberCreate) -> dict[str, Any] | None:
    if data.emergency_contact is None:
        return None
    return data.emergency_contact.model_dump(exclude_none=True)


def _build(data: MemberCreate, actor: UUID) -> Member:
    return Member(
        first_name=data.first_name,
        last_name=data.last_name,
        sex=data.sex,
        status="active",
        document_type=data.document_type,
        data_consent_at=current_clock().now_utc() if data.data_consent else None,
        data_consent_version=None,
        document=Secret.from_plain(data.document),
        phone=_secreto(data.phone),
        email=_secreto(data.email),
        birth_date=_secreto(data.birth_date),
        emergency_contact=_secreto(_contacto(data)),
        created_by=actor,
    )


def _detail(socio: Member, data: MemberCreate) -> MemberDetailOut:
    """Respuesta enmascarada desde la entrada: no se descifra nada."""
    return MemberDetailOut(
        id=socio.id,
        first_name=socio.first_name,
        last_name=socio.last_name,
        sex=data.sex,
        status="active",
        document_type=data.document_type,
        document=mask("document", data.document, document_type=data.document_type),
        phone=mask("phone", data.phone),
        email=mask("email", data.email),
        birth_date=mask("birth_date", data.birth_date),
        emergency_contact=mask("emergency_contact", _contacto(data)),
        data_consent_at=socio.data_consent_at,
        data_consent_version=None,
        deleted_at=None,
        membership_status=None,
        created_at=socio.created_at,
        updated_at=socio.updated_at,
        warnings=compute_warnings(data),
    )


async def _insert(session: AsyncSession, socio: Member, document: str) -> None:
    """La carrera la decide `uq_members_document_idx_alive` dentro de un savepoint."""
    try:
        async with session.begin_nested():
            session.add(socio)
            await session.flush()
    except IntegrityError as error:
        if DOCUMENT_ALIVE_INDEX not in str(error.orig):
            raise
        logger.info("members: alta concurrente con el mismo documento")
        raise MemberDocumentDuplicated(await id_by_document(session, document)) from None


async def create(session: AsyncSession, data: MemberCreate) -> MemberDetailOut:
    validate_member_input(data, current_clock().today_bogota())
    existente = await id_by_document(session, data.document)
    if existente is not None:
        raise MemberDocumentDuplicated(existente)
    socio = _build(data, get_actor())
    await _insert(session, socio, data.document)
    await session.refresh(socio, attribute_names=["created_at", "updated_at"])
    await events.emit(MemberCreated(member_id=socio.id), session)
    logger.info("members: socio creado", extra={"member_id": str(socio.id)})
    return _detail(socio, data)


# Contratos para otros módulos ---------------------------------------------------------


async def get_ref(session: AsyncSession, member_id: UUID) -> MemberRef:
    consulta = select(
        Member.id, Member.first_name, Member.last_name, Member.status, Member.deleted_at
    ).where(Member.id == member_id)
    fila = (await session.execute(consulta)).first()
    if fila is None:
        raise MemberNotFound()
    return MemberRef(
        id=fila.id,
        first_name=fila.first_name,
        last_name=fila.last_name,
        status=fila.status,
        is_deleted=fila.deleted_at is not None,
    )


async def ensure_exists(
    session: AsyncSession, member_id: UUID, *, include_deleted: bool = False
) -> None:
    consulta = select(Member.id).where(Member.id == member_id)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    if await session.scalar(consulta) is None:
        raise MemberNotFound()


async def id_by_document(session: AsyncSession, document: str) -> UUID | None:
    """Id del socio no borrado con ese documento (por índice ciego); `None` si no hay ninguno o
    si el valor se normaliza a vacío."""
    try:
        indice = bus.blind_index(DOCUMENT_DATA_CLASS, document)
    except CryptoError as error:
        if error.code != "empty_value":
            raise
        return None
    consulta = select(Member.id).where(Member.document_idx == indice, Member.deleted_at.is_(None))
    resultado: UUID | None = await session.scalar(consulta)
    return resultado


async def count(session: AsyncSession, *, include_deleted: bool = False) -> int:
    consulta = select(func.count()).select_from(Member)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    return int(await session.scalar(consulta) or 0)
