"""Cambios sobre el socio (S3-B10, US-075 y US-076; D21, M-3, L-1, L-7, S3-D46, S3-D54,
S3-D70): archivo privado de `members` (S3-B9a, D7, S3-D73).

Solo lo importa `members`; los demás módulos llegan por la fachada `members/service.py`, que
re-exporta las funciones y los eventos (el módulo no tiene `events.py`; el tipo del evento se
define en el emisor y se exporta desde su `service.py`, L7).

- `update(session, member_id, patch, *, role) -> MemberDetailOut`: editar. Orden:
  `ensure_can_change(patch.model_fields_set, role)` (por presencia, M-3), `data_consent=false`
  da `ConsentCannotBeWithdrawn`, `lock_member`, carga (o `MemberNotFound`), baja da
  `MemberIsDeactivated`, reglas del alta (`validate_member_patch`), pre-chequeo del documento
  entre vivos (antes de descifrar), `diff_fields` contra los valores descifrados con
  `purpose="mask"` (solo los campos cifrados presentes) y asignación con `Secret.from_plain`
  solo de lo que cambia, dentro de `begin_nested()` (la carrera la decide
  `uq_members_document_idx_alive`). Sin cambio efectivo no hay `UPDATE`, auditoría ni evento.
  `data_consent=true` fija `data_consent_at` solo si era nula. Responde la ficha de `detail.get`
  con `warnings=["data_consent_missing"]` mientras falte la autorización.
- `deactivate(session, member_id) -> None`: baja lógica (`deleted_at` del reloj y
  `status="inactive"`); no toca membresías ni pagos (N-20). Repetida, `MemberAlreadyDeactivated`.
- `reactivate(session, member_id) -> MemberDetailOut`: deshace la baja; `MemberNotDeactivated`
  sobre un vivo; documento tomado por otro vivo, `MemberDocumentDuplicated(existing_id)` (por el
  `document_idx` guardado, sin descifrar).
- `id_by_document(session, document)`: id del socio vivo con ese documento (contrato que la
  fachada re-exporta; vive aquí para que `update` lo use sin un ciclo con `service.py`).
- Eventos `MemberUpdated(member_id, changed_fields)` (nombres de columna en orden alfabético,
  nunca valores), `MemberDeactivated(member_id)` (S3-D70: la excepción 409 es
  `MemberIsDeactivated`) y `MemberReactivated(member_id)` (Fase 4 del Sprint 3, S3-D89: la
  reactivación lo emite después de `MemberUpdated`; `memberships` invalida con él y con
  `MemberDeactivated` la caché del resumen).

Las tres escrituras toman `core.locks.lock_member` antes de leer (orden único de D3: socio, plan,
membresía, pago, cadena de auditoría) y recargan la fila con `populate_existing` ya con el
candado.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import current_clock
from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.secret import Secret
from app.core.db import violated_constraint
from app.core.events import DomainEvent
from app.core.locks import lock_member
from app.core.security import Role
from app.modules.members.detail import CAMPOS_CIFRADOS, MASK_PURPOSE, _decrypt_fields, get
from app.modules.members.exceptions import (
    ConsentCannotBeWithdrawn,
    MemberAlreadyDeactivated,
    MemberDocumentDuplicated,
    MemberIsDeactivated,
    MemberNotDeactivated,
    MemberNotFound,
)
from app.modules.members.models import Member
from app.modules.members.rules import diff_fields, ensure_can_change, validate_member_patch
from app.modules.members.schemas import DATA_CONSENT_MISSING, MemberDetailOut, MemberPatch

DOCUMENT_DATA_CLASS: Final = "member.document"
DOCUMENT_ALIVE_INDEX: Final = "uq_members_document_idx_alive"
STATUS_ACTIVE: Final = "active"
STATUS_INACTIVE: Final = "inactive"
REACTIVATE_FIELDS: Final[tuple[str, ...]] = ("deleted_at", "status")
_NOMBRES: Final = frozenset({"first_name", "last_name"})


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberUpdated(DomainEvent):
    """Un socio cambió: `changed_fields` son los nombres de las columnas cambiadas, en orden
    alfabético, sin índices ciegos ni valores."""

    member_id: UUID
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberDeactivated(DomainEvent):
    """Un socio fue dado de baja (N-20: sus membresías y pagos no cambian)."""

    member_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberReactivated(DomainEvent):
    """Un socio dado de baja volvió a estar vivo (S3-D89: `memberships` lo escucha para
    invalidar la caché del resumen). Solo el id, sin datos personales."""

    member_id: UUID


# Documento entre vivos ----------------------------------------------------------------


async def id_by_document(session: AsyncSession, document: str) -> UUID | None:
    """Id del socio no borrado con ese documento (por índice ciego); `None` si no hay ninguno o
    si el valor se normaliza a vacío."""
    try:
        indice = bus.blind_index(DOCUMENT_DATA_CLASS, document)
    except CryptoError as error:
        if error.code != "empty_value":
            raise
        return None
    return await _vivo_con_indice(session, indice)


async def _vivo_con_indice(
    session: AsyncSession, indice: str, *, excepto: UUID | None = None
) -> UUID | None:
    """Id del socio vivo con ese `document_idx` (distinto de `excepto`), sin descifrar."""
    consulta = select(Member.id).where(Member.document_idx == indice, Member.deleted_at.is_(None))
    if excepto is not None:
        consulta = consulta.where(Member.id != excepto)
    resultado: UUID | None = await session.scalar(consulta)
    return resultado


Ganador = Callable[[], Coroutine[Any, Any, UUID | None]]


async def _escribir(session: AsyncSession, asignar: Callable[[], None], ganador: Ganador) -> None:
    """Asigna y hace flush DENTRO de un savepoint: si `uq_members_document_idx_alive` decide la
    carrera, el savepoint se revierte sin dejar la sesión en `PendingRollbackError` y el 409 lleva
    el id del socio vivo que ganó (`ganador`)."""
    try:
        async with session.begin_nested():
            asignar()
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != DOCUMENT_ALIVE_INDEX:
            raise
        raise MemberDocumentDuplicated(await ganador()) from None


async def _bloquear_y_cargar(session: AsyncSession, member_id: UUID) -> Member:
    """`lock_member` y después la fila fresca (`populate_existing`) o `MemberNotFound`."""
    await lock_member(session, member_id)
    consulta = (
        select(Member).where(Member.id == member_id).execution_options(populate_existing=True)
    )
    socio = await session.scalar(consulta)
    if socio is None:
        raise MemberNotFound()
    return socio


# Editar (US-075) ----------------------------------------------------------------------


def _actuales(socio: Member, campos: frozenset[str]) -> dict[str, object]:
    """Los valores actuales en claro de los campos presentes; solo descifra los cifrados que el
    patch trae (`purpose="mask"`, D20)."""
    cifrados = [campo for campo in CAMPOS_CIFRADOS if campo in campos]
    return {
        "first_name": socio.first_name,
        "last_name": socio.last_name,
        "sex": socio.sex,
        "document_type": socio.document_type,
        **_decrypt_fields(socio, cifrados, MASK_PURPOSE),
    }


def _valor_nuevo(patch: MemberPatch, campo: str) -> object:
    """El valor de columna de `campo`: los cifrados como `Secret.from_plain` (o `None`), los
    nombres en NFC y el contacto como mapeo sin nulos."""
    valor: Any = getattr(patch, campo)
    if campo in _NOMBRES:
        return unicodedata.normalize("NFC", valor)
    if campo not in CAMPOS_CIFRADOS or valor is None:
        return valor
    if campo == "emergency_contact":
        return Secret.from_plain(valor.model_dump(exclude_none=True))
    return Secret.from_plain(valor)


def _cambios(socio: Member, patch: MemberPatch) -> list[str]:
    """Las columnas que el patch cambia, en orden alfabético (con `data_consent_at` cuando
    `data_consent=true` llega sobre una autorización nula)."""
    cambios = set(diff_fields(_actuales(socio, frozenset(patch.model_fields_set)), patch))
    if patch.data_consent is True and socio.data_consent_at is None:
        cambios.add("data_consent_at")
    return sorted(cambios)


async def _ficha(session: AsyncSession, socio: Member) -> MemberDetailOut:
    """La ficha enmascarada con el aviso de autorización pendiente (M-4)."""
    ficha = await get(session, socio.id)
    if socio.data_consent_at is not None:
        return ficha
    return ficha.model_copy(update={"warnings": [DATA_CONSENT_MISSING]})


def _asignador(socio: Member, patch: MemberPatch, cambios: list[str]) -> Callable[[], None]:
    def asignar() -> None:
        for campo in cambios:
            if campo == "data_consent_at":
                socio.data_consent_at = current_clock().now_utc()
            else:
                setattr(socio, campo, _valor_nuevo(patch, campo))

    return asignar


async def _documento_libre(session: AsyncSession, member_id: UUID, patch: MemberPatch) -> None:
    """Pre-chequeo del documento del patch entre los vivos (sin el propio socio), ANTES de
    descifrar nada: un 409 no deja filas `decrypt` (que sobreviven al rollback, D19)."""
    if patch.document is None:
        return
    existente = await id_by_document(session, patch.document)
    if existente is not None and existente != member_id:
        raise MemberDocumentDuplicated(existente)


async def _ganador_del_documento(session: AsyncSession, patch: MemberPatch) -> UUID | None:
    """El socio vivo que se quedó con el documento del patch al perder la carrera."""
    return None if patch.document is None else await id_by_document(session, patch.document)


async def update(
    session: AsyncSession, member_id: UUID, patch: MemberPatch, *, role: Role
) -> MemberDetailOut:
    """Edita el socio (US-075): ningún error deja cambios parciales; sin cambio efectivo no hay
    `UPDATE`, auditoría ni evento."""
    ensure_can_change(patch.model_fields_set, role)
    if patch.data_consent is False:
        raise ConsentCannotBeWithdrawn()
    socio = await _bloquear_y_cargar(session, member_id)
    if socio.deleted_at is not None:
        raise MemberIsDeactivated()
    validate_member_patch(patch, current_clock().today_bogota())
    await _documento_libre(session, member_id, patch)
    cambios = _cambios(socio, patch)
    if not cambios:
        return await _ficha(session, socio)
    await _escribir(
        session,
        _asignador(socio, patch, cambios),
        lambda: _ganador_del_documento(session, patch),
    )
    await events.emit(MemberUpdated(member_id=member_id, changed_fields=tuple(cambios)), session)
    return await _ficha(session, socio)


# Baja y reactivación (US-076) ---------------------------------------------------------


async def deactivate(session: AsyncSession, member_id: UUID) -> None:
    """Baja lógica del socio (US-076): `deleted_at` del reloj (UTC) y `status="inactive"`; una
    fila `update` del hook y `MemberDeactivated`. Sus membresías y pagos no cambian (N-20)."""
    socio = await _bloquear_y_cargar(session, member_id)
    if socio.deleted_at is not None:
        raise MemberAlreadyDeactivated()
    socio.deleted_at = current_clock().now_utc()
    socio.status = STATUS_INACTIVE
    await session.flush()
    await events.emit(MemberDeactivated(member_id=member_id), session)


async def reactivate(session: AsyncSession, member_id: UUID) -> MemberDetailOut:
    """Deshace la baja del socio (US-076, N-20): `deleted_at` nulo y `status="active"`, auditado
    por el hook, con `MemberUpdated(("deleted_at", "status"))` y después `MemberReactivated`
    (S3-D89). El documento tomado por otro
    socio vivo da `MemberDocumentDuplicated` y la fila sigue dada de baja."""
    socio = await _bloquear_y_cargar(session, member_id)
    if socio.deleted_at is None:
        raise MemberNotDeactivated()
    indice = socio.document_idx
    existente = await _vivo_con_indice(session, indice, excepto=member_id)
    if existente is not None:
        raise MemberDocumentDuplicated(existente)

    def asignar() -> None:
        socio.deleted_at = None
        socio.status = STATUS_ACTIVE

    await _escribir(session, asignar, lambda: _vivo_con_indice(session, indice, excepto=member_id))
    evento = MemberUpdated(member_id=member_id, changed_fields=REACTIVATE_FIELDS)
    await events.emit(evento, session)
    await events.emit(MemberReactivated(member_id=member_id), session)
    return await _ficha(session, socio)
