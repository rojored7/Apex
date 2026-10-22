"""Caso de uso de socios (S2-B7, US-069; M-4, M-5, L-1, L-3).

Puras:
- `validate_member_input(data, today)`: nombres no vacíos, `sex` en `f`/`m`/`x` o nulo,
  `1900-01-01 <= birth_date <= today` (`today` es `today_bogota()`), documento o correo
  que no se normalicen a vacío y teléfono con al menos `PHONE_MIN_DIGITS` dígitos tras
  normalizar (L-3: `"+57"` se normaliza a `"57"`). Lanza
  `MemberValidationError` con `field` y sin repetir el valor.
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

Buscar y listar (S2-B8, US-070; RN-13, RN-14, N-01, N-20, L-1):
- `classify_query(q) -> QueryPlan` (pura): `q` en NFC, sin caracteres de control y
  recortado; `name_pattern` = `%<q>%` con la barra invertida, `%` y `_` escapados
  (`LIKE_ESCAPE`); `by_document` = el documento
  normalizado (`generic`) cuando no queda vacío, tiene al menos un dígito y solo letras y
  dígitos; `by_phone` = el teléfono normalizado con al menos `PHONE_MIN_DIGITS` dígitos;
  `by_email` = el correo normalizado si `q` tiene `@`. Captura `CryptoError("empty_value")`.
  `q` vacío o en blanco da el plan vacío (todo `None`).
- `list(session, filters, page)`: dentro de `bus.batch("index", None)` calcula con
  `bus.blind_index` solo los índices del plan; `UNION` de subconsultas de ids (una por índice y
  una por `ILIKE` sobre `first_name || ' ' || last_name`, sin tildes ni mayúsculas); `status`
  (`deleted` = `deleted_at IS NOT NULL`; `active`/`inactive` = vivos con ese estado; sin
  filtro = vivos), `sort` y `paginate`. Nunca descifra (cero `decrypt` en `crypto_ops`).
- `search_ids(session, q, include_deleted=False)` y `names_for(session, ids)`: una consulta
  cada una; `names_for` incluye dados de baja (contratos de US-091 y US-110).
"""

from __future__ import annotations

import builtins
import logging
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CompoundSelect,
    Select,
    Text,
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
from app.core.crypto.errors import CryptoError
from app.core.crypto.normalize import IndexKind, normalize_for_index
from app.core.crypto.secret import PlainValue, Secret
from app.core.db import violated_constraint
from app.core.events import DomainEvent
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
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
    MemberListQuery,
    MemberName,
    MemberRef,
    MemberRowOut,
)

logger = logging.getLogger("app.members")

MaskField = Literal["document", "phone", "email", "birth_date", "emergency_contact"]
MaskValue = str | date | Mapping[str, Any] | None

DOCUMENT_DATA_CLASS: Final = "member.document"
DOCUMENT_ALIVE_INDEX: Final = "uq_members_document_idx_alive"
BIRTH_DATE_MIN: Final = date(1900, 1, 1)  # LOW L6: un año mal tecleado (`0991`) no pasa
PHONE_MIN_DIGITS: Final = 7  # L-3: "+57" queda en "57"; un fijo local tiene 7 dígitos
MASK_TAIL: Final = 4
DOCUMENT_MIN_MASKED: Final = 6  # al menos 2 caracteres ocultos además de la cola
DOTS: Final = "•••"
EMERGENCY_CONTACT_MASK: Final = "Registrado"
PHONE_DATA_CLASS: Final = "member.phone"
EMAIL_DATA_CLASS: Final = "member.email"

_MENSAJES: Final[Mapping[str, str]] = {
    "first_name": "El nombre es obligatorio.",
    "last_name": "El apellido es obligatorio.",
    "sex": "El sexo debe ser f, m o x.",
    "birth_date": "La fecha de nacimiento debe estar entre 1900 y hoy.",
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
    """Reglas del alta que el schema no expresa (L-3; LOW L6 de la revisión Python: fecha de
    nacimiento entre `BIRTH_DATE_MIN` y `today`). Lanza `MemberValidationError` con `field` y
    sin repetir el valor."""
    for campo in ("first_name", "last_name"):
        if not str(getattr(data, campo) or "").strip():
            raise _invalido(campo)
    if data.sex is not None and data.sex not in SEXES:
        raise _invalido("sex")
    if data.birth_date is not None and not BIRTH_DATE_MIN <= data.birth_date <= today:
        raise _invalido("birth_date")
    if not _normalizado(data.document, "generic"):
        raise _invalido("document")
    if data.phone is not None and len(_normalizado(data.phone, "phone")) < PHONE_MIN_DIGITS:
        raise _invalido("phone")
    if data.email is not None and not _normalizado(data.email, "email"):
        raise _invalido("email")


def compute_warnings(data: MemberCreate) -> builtins.list[str]:
    """Avisos del alta: `data_consent_missing` sin autorización (M-4)."""
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
    """Socios vivos (o todos con `include_deleted`)."""
    consulta = select(func.count()).select_from(Member)
    if not include_deleted:
        consulta = consulta.where(Member.deleted_at.is_(None))
    return int(await session.scalar(consulta) or 0)


# Buscar y listar (S2-B8) --------------------------------------------------------------


@dataclass(frozen=True)
class QueryPlan:
    """Qué busca un término: patrón de nombre y valores normalizados para cada índice ciego."""

    q: str | None
    name_pattern: str | None
    by_document: str | None
    by_phone: str | None
    by_email: str | None


PLAN_VACIO: Final = QueryPlan(
    q=None, name_pattern=None, by_document=None, by_phone=None, by_email=None
)


def _es_documento(normalizado: str) -> bool:
    """CC, CE, TI y PA: solo letras y dígitos ASCII y al menos un dígito (S2-B8, decisión 1)."""
    return normalizado.isascii() and normalizado.isalnum() and any(c.isdigit() for c in normalizado)


def classify_query(q: str | None) -> QueryPlan:
    """El plan de búsqueda de `q` (`core.search.clean_query`: NFC, sin `Cc`, recortado; defensa
    en profundidad, `SearchQuery` ya rechaza los controles con 422)."""
    termino = clean_query(q)
    if not termino:
        return PLAN_VACIO
    documento = _normalizado(termino, "generic")
    telefono = _normalizado(termino, "phone")
    correo = _normalizado(termino, "email") if "@" in termino else ""
    return QueryPlan(
        q=termino,
        name_pattern=contains_pattern(termino),
        by_document=documento if _es_documento(documento) else None,
        by_phone=telefono if len(telefono) >= PHONE_MIN_DIGITS else None,
        by_email=correo or None,
    )


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


def _fila(socio: Member) -> MemberRowOut:
    """Solo columnas en claro (N-01): ni el blob ni la máscara."""
    return MemberRowOut.model_validate(
        {
            "id": socio.id,
            "first_name": socio.first_name,
            "last_name": socio.last_name,
            "sex": socio.sex,
            "status": socio.status,
            "deleted_at": socio.deleted_at,
            "membership_status": None,
            "plan_name": None,
        }
    )


async def list(  # nombre del contrato del blueprint B8 (las anotaciones usan builtins.list)
    session: AsyncSession, filters: MemberListQuery, page: PageParams
) -> Page[MemberRowOut]:
    """US-070: la página de socios filtrada; nunca descifra (N-01)."""
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
    socios, total = await paginate(session, consulta.order_by(*_ORDEN[filters.sort]), page)
    return to_page([_fila(s) for s in socios], total, page)


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
