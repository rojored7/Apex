"""Fachada del service de socios (S2-B7, US-069; S2-B8, US-070; S3-B9a, D7, S3-D73).

Otros módulos (`memberships`, `payments`), el router y las pruebas solo importan este archivo
(regla de módulos 2): re-exporta con `__all__` lo público de los archivos privados del módulo
(`PRIVATE_HELPERS["members"]`):
- `rules.py`: las puras y los tipos (`validate_member_input`, `compute_warnings`, `mask`,
  `classify_query`, `QueryPlan`, `LIKE_ESCAPE`, `PHONE_DATA_CLASS`, `EMAIL_DATA_CLASS`) y,
  desde S3-B9b, `chip_to_filter`, `MemberChipFilter` y `MEMBER_CHIPS`; desde S3-B10,
  `diff_fields`, `ensure_can_change` y `ADMIN_ONLY_FIELDS`;
- `detail.py` (S3-B9b): `get(session, member_id)`, la ficha enmascarada (US-073); desde S3-B10
  `reveal(session, member_id, field, *, ip)` (US-074);
- `changes.py` (S3-B10): `update`, `deactivate`, `reactivate` y los eventos `MemberUpdated`,
  `MemberDeactivated` y `MemberReactivated` (S3-D89) (US-075, US-076); también `id_by_document`,
  `DOCUMENT_DATA_CLASS` y `DOCUMENT_ALIVE_INDEX`, que se mudaron allí para que `update` los use
  sin un ciclo con este archivo (la fachada los sigue exportando).

S3-B9b (US-071; D22, G-03, G-04): `list` acepta `membership_status` y `plan_id`; el conjunto de
ids lo pide a `memberships.service.member_ids_by_status` con import perezoso (`# lazy: G-03
(members -> memberships)`) y lo aplica con `Member.id == any_(...)` (o `!= all_(...)` para
`none`) en la consulta externa; cada página se decora con UNA llamada a
`memberships.service.status_for(ids)` (`membership_status`, `plan_name`,
`membership_end_date`; sin entrada, `none`).

Con sesión (siguen aquí):
- `create(session, data)`: valida, pre-chequea el documento por índice ciego, arma el `Member`
  con `Secret.from_plain`, `data_consent_at = clock.now_utc()` si `data_consent` (M-4) y
  `data_consent_version = None`; la carrera la decide `uq_members_document_idx_alive` dentro de
  `begin_nested()`; emite `MemberCreated`; responde enmascarado sin descifrar nada. El actor sale
  de `current_actor`.
- Contratos para otros módulos: `get_ref`, `ensure_exists`, `id_by_document`, `count` y
  `active_ids` (S3-B7, S3-D60: los ids de los socios no dados de baja, para el resumen de
  `memberships`).

Buscar y listar (S2-B8, US-070; RN-13, RN-14, N-01, N-20, L-1):
- `list(session, filters, page)`: dentro de `bus.batch("index", None)` calcula con
  `bus.blind_index` solo los índices del plan de `classify_query`; `UNION` de subconsultas de
  ids (una por índice y una por `ILIKE` sobre `first_name || ' ' || last_name`, sin tildes ni
  mayúsculas); `status` (`deleted` = `deleted_at IS NOT NULL`; `active`/`inactive` = vivos con
  ese estado; sin filtro = vivos), `sort` y `paginate`. Nunca descifra (cero `decrypt` en
  `crypto_ops`).
- `search_ids(session, q, include_deleted=False)` y `names_for(session, ids)`: una consulta
  cada una; `names_for` incluye dados de baja (contratos de US-091 y US-110).

Historial (S4A-B5, US-106; S4A-D20): `history(session, member_id, page, q)` hace
`ensure_exists(member_id, include_deleted=True)` y delega en `audit.service.member_history`
(import de nivel de módulo: arista `members -> audit`; `audit` nunca importa `members`).
"""

from __future__ import annotations

import builtins
import logging
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CompoundSelect,
    Select,
    Text,
    all_,
    func,
    literal,
    select,
    union,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.crypto import bus
from app.core.crypto.secret import PlainValue, Secret
from app.core.db import violated_constraint
from app.core.events import DomainEvent
from app.core.pagination import Page, PageParams, any_uuids, paginate, to_page, uuid_array
from app.core.search import sql_fold

# Arista `members -> audit` de nivel de módulo (S4A-D20): el historial del socio.
from app.modules.audit import service as audit_service
from app.modules.audit.schemas import MemberHistoryItem
from app.modules.members.changes import (
    DOCUMENT_ALIVE_INDEX,
    DOCUMENT_DATA_CLASS,
    MemberDeactivated,
    MemberReactivated,
    MemberUpdated,
    deactivate,
    id_by_document,
    reactivate,
    update,
)
from app.modules.members.detail import SIN_MEMBRESIA, get, reveal
from app.modules.members.exceptions import MemberDocumentDuplicated, MemberNotFound
from app.modules.members.models import Member
from app.modules.members.rules import (
    ADMIN_ONLY_FIELDS,
    EMAIL_DATA_CLASS,
    LIKE_ESCAPE,
    MEMBER_CHIPS,
    PHONE_DATA_CLASS,
    MemberChipFilter,
    QueryPlan,
    chip_to_filter,
    classify_query,
    compute_warnings,
    diff_fields,
    ensure_can_change,
    mask,
    validate_member_input,
)
from app.modules.members.schemas import (
    MemberCreate,
    MemberDetailOut,
    MemberListQuery,
    MemberName,
    MemberRef,
    MemberRowOut,
)

if TYPE_CHECKING:  # solo el tipo del contrato de `status_for` (regla de módulos 2)
    from app.modules.memberships.schemas import MemberMembership

__all__ = [
    "ADMIN_ONLY_FIELDS",
    "DOCUMENT_ALIVE_INDEX",
    "DOCUMENT_DATA_CLASS",
    "EMAIL_DATA_CLASS",
    "LIKE_ESCAPE",
    "MEMBER_CHIPS",
    "PHONE_DATA_CLASS",
    "MemberChipFilter",
    "MemberCreated",
    "MemberDeactivated",
    "MemberReactivated",
    "MemberUpdated",
    "QueryPlan",
    "active_ids",
    "chip_to_filter",
    "classify_query",
    "compute_warnings",
    "count",
    "create",
    "deactivate",
    "diff_fields",
    "ensure_can_change",
    "ensure_exists",
    "get",
    "get_ref",
    "history",
    "id_by_document",
    "list",
    "mask",
    "names_for",
    "reactivate",
    "reveal",
    "search_ids",
    "update",
    "validate_member_input",
]

logger = logging.getLogger("app.members")

# Los cinco estados con membresía que decide (D22); `none` es su complemento.
_CON_MEMBRESIA: Final = ("active", "expiring", "expired", "frozen", "pending_payment")


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberCreated(DomainEvent):
    """Un socio quedó insertado en la transacción (solo el id, sin datos personales)."""

    member_id: UUID


# Alta ---------------------------------------------------------------------------------


def _secreto(valor: PlainValue | None) -> Secret | None:
    return None if valor is None else Secret.from_plain(valor)


def _contacto(data: MemberCreate) -> dict[str, Any] | None:
    if data.emergency_contact is None:
        return None
    return data.emergency_contact.model_dump(exclude_none=True)


def _build(data: MemberCreate, actor: UUID) -> Member:
    """El `Member` del alta; los nombres en NFC aunque el que llama no pase por el schema
    (Python H2: así "José" compuesto y descompuesto se buscan y ordenan igual)."""
    return Member(
        first_name=unicodedata.normalize("NFC", data.first_name),
        last_name=unicodedata.normalize("NFC", data.last_name),
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
        membership_status=SIN_MEMBRESIA,  # PL4 de Fase 4: un socio recién creado no tiene membresía
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
        if violated_constraint(error) != DOCUMENT_ALIVE_INDEX:
            raise
        logger.info("members: alta concurrente con el mismo documento")
        raise MemberDocumentDuplicated(await id_by_document(session, document)) from None


async def create(session: AsyncSession, data: MemberCreate) -> MemberDetailOut:
    """Alta de un socio (US-069): valida, rechaza el documento repetido, cifra y emite
    `MemberCreated`; responde enmascarado desde la entrada, sin descifrar."""
    validate_member_input(data, current_clock().today_bogota())
    existente = await id_by_document(session, data.document)
    if existente is not None:
        raise MemberDocumentDuplicated(existente)
    socio = _build(data, get_actor())
    await _insert(session, socio, data.document)  # `eager_defaults`: fechas ya cargadas (M4)
    await events.emit(MemberCreated(member_id=socio.id), session)
    logger.info("members: socio creado", extra={"member_id": str(socio.id)})
    return _detail(socio, data)


# Contratos para otros módulos ---------------------------------------------------------


async def get_ref(session: AsyncSession, member_id: UUID) -> MemberRef:
    """Contrato para otros módulos: el socio (incluye dados de baja) o `MemberNotFound`."""
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
    """`MemberNotFound` si no existe (o está dado de baja, salvo `include_deleted`)."""
    consulta = select(Member.id).where(Member.id == member_id)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    if await session.scalar(consulta) is None:
        raise MemberNotFound()


async def count(session: AsyncSession, *, include_deleted: bool = False) -> int:
    """Socios vivos (o todos con `include_deleted`)."""
    consulta = select(func.count()).select_from(Member)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    return int(await session.scalar(consulta) or 0)


async def active_ids(session: AsyncSession) -> frozenset[UUID]:
    """Ids de los socios no dados de baja (`deleted_at IS NULL`), activos o inactivos, en una
    consulta y sin descifrar (S3-B7, S3-D60; contrato de `memberships.summary`)."""
    return frozenset(await session.scalars(select(Member.id).where(Member.deleted_at.is_(None))))


# Buscar y listar (S2-B8) --------------------------------------------------------------


@dataclass(frozen=True)
class _Indices:
    document: str | None
    phone: str | None
    email: str | None


def _indices(plan: QueryPlan) -> _Indices:
    """Índices ciegos del plan en un único lote de `crypto_ops`; ninguno si no hay valores."""
    pares = (
        (DOCUMENT_DATA_CLASS, plan.by_document),
        (PHONE_DATA_CLASS, plan.by_phone),
        (EMAIL_DATA_CLASS, plan.by_email),
    )
    if all(valor is None for _, valor in pares):
        return _Indices(None, None, None)
    with bus.batch("index", None):
        document, phone, email = (
            None if valor is None else bus.blind_index(clase, valor) for clase, valor in pares
        )
    return _Indices(document, phone, email)


def _vivo_o_baja(*, deleted: bool) -> ColumnElement[bool]:
    return Member.deleted_at.is_not(None) if deleted else Member.deleted_at.is_(None)


def _ramas(
    plan: QueryPlan, indices: _Indices, deleted_cond: ColumnElement[bool] | None
) -> builtins.list[Select[UUID]]:
    """Una subconsulta de ids por índice y una por nombre. Cada una lleva su condición de baja
    para que la de documento use el único parcial `uq_members_document_idx_alive`."""
    condiciones: builtins.list[ColumnElement[bool]] = []
    if indices.document is not None:
        condiciones.append(Member.document_idx == indices.document)
    if indices.phone is not None:
        condiciones.append(Member.phone_idx == indices.phone)
    if indices.email is not None:
        condiciones.append(Member.email_idx == indices.email)
    if plan.name_pattern is not None:
        nombre = sql_fold(Member.first_name + " " + Member.last_name)
        patron = sql_fold(literal(plan.name_pattern, Text))  # valor ligado
        condiciones.append(nombre.ilike(patron, escape=LIKE_ESCAPE))
    ramas: builtins.list[Select[UUID]] = []
    for condicion in condiciones:
        rama = select(Member.id).where(condicion)
        ramas.append(rama if deleted_cond is None else rama.where(deleted_cond))
    return ramas


def _ids_que_coinciden(
    plan: QueryPlan, deleted_cond: ColumnElement[bool] | None
) -> CompoundSelect[UUID] | Select[UUID]:
    ramas = _ramas(plan, _indices(plan), deleted_cond)
    return ramas[0] if len(ramas) == 1 else union(*ramas)


def _filtro_de_estado(estado: str | None) -> builtins.list[ColumnElement[bool]]:
    """`deleted` = dados de baja (también inactivos); `active`/`inactive` = vivos con ese
    estado; sin filtro = vivos (N-20: igual para admin y coach). El primero es la condición de
    baja que repite cada rama de la búsqueda."""
    if estado == "deleted":
        return [_vivo_o_baja(deleted=True)]
    if estado is None:
        return [_vivo_o_baja(deleted=False)]
    return [_vivo_o_baja(deleted=False), Member.status == estado]


_ORDEN: Final[Mapping[str, tuple[ColumnElement[Any], ...]]] = {
    "last_name": (Member.last_name.asc(), Member.first_name.asc()),
    "-last_name": (Member.last_name.desc(), Member.first_name.desc()),
    "first_name": (Member.first_name.asc(), Member.last_name.asc()),
    "-first_name": (Member.first_name.desc(), Member.last_name.desc()),
    "created_at": (Member.created_at.asc(),),
    "-created_at": (Member.created_at.desc(),),
}


def _fila(socio: Member, membresia: MemberMembership | None) -> MemberRowOut:
    """Solo columnas en claro (N-01): ni el blob ni la máscara. Sin membresía que decida,
    `none` y plan y fin nulos (blueprint B7)."""
    return MemberRowOut.model_validate(
        {
            "id": socio.id,
            "first_name": socio.first_name,
            "last_name": socio.last_name,
            "sex": socio.sex,
            "status": socio.status,
            "deleted_at": socio.deleted_at,
            "membership_status": SIN_MEMBRESIA if membresia is None else membresia.status,
            "plan_name": None if membresia is None else membresia.plan_name,
            "membership_end_date": None if membresia is None else membresia.end_date,
        }
    )


async def _filas(session: AsyncSession, socios: Sequence[Member]) -> builtins.list[MemberRowOut]:
    """Decora la página con UNA llamada a `memberships.service.status_for` (G-04); una página
    vacía no consulta nada."""
    if not socios:
        return []
    # lazy: G-03 (members -> memberships)
    from app.modules.memberships import service as memberships_service

    estados = await memberships_service.status_for(session, [s.id for s in socios])
    return [_fila(s, estados.get(s.id)) for s in socios]


async def _por_membresia(
    session: AsyncSession, filters: MemberListQuery
) -> ColumnElement[bool] | None:
    """Condición de la consulta externa por `membership_status` y `plan_id` (D22): `None` sin
    esos filtros. El conjunto lo resuelve `memberships`; `none` es el complemento de los cinco
    estados y `plan_id` solo mira los cinco (el llamador corta `none` + `plan_id` antes)."""
    if filters.membership_status is None and filters.plan_id is None:
        return None
    # lazy: G-03 (members -> memberships)
    from app.modules.memberships import service as memberships_service

    if filters.membership_status == SIN_MEMBRESIA:
        con = await memberships_service.member_ids_by_status(session, _CON_MEMBRESIA)
        # Un solo parámetro `uuid[]` (D22, S3-D71): 5.000 ids no expanden un `IN`.
        return Member.id != all_(uuid_array(con))
    estados = _CON_MEMBRESIA if filters.membership_status is None else (filters.membership_status,)
    ids = await memberships_service.member_ids_by_status(session, estados, filters.plan_id)
    return Member.id == any_uuids(ids)


async def list(  # nombre del contrato del blueprint B8 (las anotaciones usan builtins.list)
    session: AsyncSession, filters: MemberListQuery, page: PageParams
) -> Page[MemberRowOut]:
    """US-070 y US-071: la página de socios filtrada y decorada; nunca descifra (N-01)."""
    if filters.membership_status == SIN_MEMBRESIA and filters.plan_id is not None:
        return to_page([], 0, page)  # sin membresía no hay plan: ni se consulta (D22)
    estado = _filtro_de_estado(filters.status)
    consulta = (
        select(Member)
        .options(
            load_only(
                Member.first_name,
                Member.last_name,
                Member.sex,
                Member.status,
                Member.deleted_at,
            )
        )
        .where(*estado)
    )
    plan = classify_query(filters.q)
    if plan.q is not None:
        consulta = consulta.where(Member.id.in_(_ids_que_coinciden(plan, estado[0])))
    por_membresia = await _por_membresia(session, filters)
    if por_membresia is not None:
        consulta = consulta.where(por_membresia)
    socios, total = await paginate(session, consulta.order_by(*_ORDEN[filters.sort]), page)
    return to_page(await _filas(session, socios), total, page)


async def search_ids(session: AsyncSession, q: str, *, include_deleted: bool = False) -> set[UUID]:
    """Ids de los socios que coinciden con `q`, en una sentencia; `q` en blanco da `set()`."""
    plan = classify_query(q)
    if plan.q is None:
        return set()
    condicion = None if include_deleted else _vivo_o_baja(deleted=False)
    return set(await session.scalars(_ids_que_coinciden(plan, condicion)))


async def names_for(session: AsyncSession, ids: Iterable[UUID]) -> dict[UUID, MemberName]:
    """Nombre y sexo de cada id existente, incluidos los dados de baja, en una consulta."""
    buscados = builtins.list(dict.fromkeys(ids))
    if not buscados:
        return {}
    consulta = select(Member.id, Member.first_name, Member.last_name, Member.sex).where(
        Member.id.in_(buscados)
    )
    return {
        fila.id: MemberName(
            id=fila.id, first_name=fila.first_name, last_name=fila.last_name, sex=fila.sex
        )
        for fila in await session.execute(consulta)
    }


# Historial del socio (S4A-B5, US-106; S4A-D20) -----------------------------------------


async def history(
    session: AsyncSession, member_id: UUID, page: PageParams, q: str | None
) -> Page[MemberHistoryItem]:
    """El historial del socio (también dado de baja) o `MemberNotFound`; delega en
    `audit.service.member_history` (arista de nivel de módulo `members -> audit`, S4A-D20)."""
    await ensure_exists(session, member_id, include_deleted=True)
    return await audit_service.member_history(session, member_id, page, q)
