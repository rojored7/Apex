"""Lectura de la auditoría: lista y detalle (S4A-B4, US-102 y US-103; S4A-D16, S4A-D17, S4A-D18,
S4A-D45, S4A-D46, S4A-D61).

Privado de `audit` (`PRIVATE_HELPERS["audit"]`); los demás módulos y el router lo ven por la
fachada `service.py`.

- `AUDITABLE_TABLES` (S4A-D61 b): la constante única de las tablas auditadas (`esquema.tabla`).
- `AuditFilters` (dataclass congelada) y `build_audit_filters(query, page, *, now)` (pura): pasa
  `AuditListQuery` a filtros. `q` que es un UUID filtra `record_id` solo si hay `table` y no hay
  `record_id` explícito (S4A-D104, S4A-D106 a); otro texto se limpia con
  `core.search.clean_query` y queda en `email_term` (correo de quien actuó); vacío no filtra.
  `from`/`to` con `core.validators.check_instant_range` (piso 2020-01-01, techo `now + 1 día`,
  `from < to`), `page.offset <= MAX_AUDIT_OFFSET`, `table` dentro de `AUDITABLE_TABLES` y
  `record_id` solo con `table` (S4A-D106 a: el conteo usa `(table_name, record_id)`); si no,
  `AuditRangeInvalid` con `field` (`from`, `to`, `offset`, `table` o `record_id`).
- `list(session, filters, page) -> Page[AuditRow]`: `select(AuditEntry)` con los filtros
  (igualdad; rango `[start, end)`; `email_term` por `auth.service.search_user_ids`), `ORDER BY
  seq DESC`, `paginate` con el conteo acotado a `MAX_AUDIT_OFFSET + 1` (S4A-D106 b: `total` se
  satura en 100.001); quién actuó por `auth.service.user_refs_for` en un lote por página. Solo
  lee: nunca escribe ni audita la lectura (S4A-D61 c).
- `get(session, seq) -> AuditDetail`: la fila completa con `before`/`after` pasados por
  `diff.redact_blobs` y `changes = diff.diff(...)`; nunca descifra ni importa el bus (S4A-D17).
  `AuditEntryNotFound` si no existe.
- `member_history(session, member_id, page, q) -> Page[MemberHistoryItem]` (S4A-B5, US-106;
  S4A-D20): las entradas con `subject_member_id` del socio, sin correo ni valores; nombres por
  `auth.service.user_names_for` (S4A-D54).
- `recent(session, tables, limit, *, actions, exclude_user_ids) -> list[AuditEntryView]` (S4A-B8,
  US-110; S4A-D28, S4A-D51): las últimas filas de las tablas pedidas, una consulta por tabla
  (`table_name = :t AND action = ANY(:acciones) AND user_id <> ALL(:excluidos) ORDER BY seq DESC
  LIMIT :limit`, por `ix_audit_log_table_seq`), unidas por `seq` descendente en memoria y
  recortadas a `limit`; cada una pasa por `diff.reduce_entry`. `tables` dentro de
  `RECENT_TABLES_ALLOWED` y `limit` de 1 a `MAX_RECENT_LIMIT`; si no, `ValueError`. Solo lee.
- `RECENT_TABLES_ALLOWED` (S4A-D61 b): `AUDITABLE_TABLES` menos
  `AUDIT_TABLES_EXCLUDED_FROM_RECENT` (cada excluida con su motivo).
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, all_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, AuditEntry
from app.core.pagination import Page, PageParams, any_uuids, paginate, to_page, uuid_array
from app.core.search import clean_query
from app.core.validators import check_instant_range
from app.modules.audit import diff
from app.modules.audit.exceptions import AuditEntryNotFound, AuditRangeInvalid
from app.modules.audit.schemas import (
    MAX_AUDIT_OFFSET,
    AuditDetail,
    AuditEntryView,
    AuditListQuery,
    AuditRow,
    MemberHistoryItem,
)

# Arista `audit → auth` del grafo de services (S4A-D19): import a nivel de módulo (duda e).
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import UserRef

AUDITABLE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "members.members",
        "memberships.memberships",
        "memberships.membership_freezes",
        "payments.payments",
        "plans.plans",
        "auth.users",
        "auth.one_time_tokens",
        "settings.settings_sections",
        "audit.verifications",
    }
)
AUDIT_TABLES_EXCLUDED_FROM_RECENT: Final[Mapping[str, str]] = {
    "memberships.membership_freezes": "aparece por el update de la membresía",
    "auth.one_time_tokens": "técnica",
    "audit.verifications": "es la verificación misma",
}
"""Tablas auditadas que `recent` nunca lee, con su motivo (S4A-D61 b)."""
RECENT_TABLES_ALLOWED: Final[frozenset[str]] = AUDITABLE_TABLES - frozenset(
    AUDIT_TABLES_EXCLUDED_FROM_RECENT
)
"""Lista blanca de `recent` (S4A-D28): las seis tablas de negocio y configuración."""
MAX_RECENT_LIMIT: Final = 50
"""Tope de `limit` en `recent` (S4A-D51: como mucho 6 x 50 filas se unen en memoria)."""
RECENT_ACTIONS: Final[tuple[AuditAction, ...]] = ("insert", "update", "delete")
"""Acciones por defecto de `recent`: las escrituras (nunca lecturas como `reveal` o `login`)."""
DOMAIN_SEPARATOR: Final = "@"
"""Un `q` del historial con `@` no es una parte local: página vacía sin consultar (S4A-D112)."""
UNKNOWN_TABLE_MESSAGE: Final = "Esa tabla no está en la auditoría."
RECORD_WITHOUT_TABLE_MESSAGE: Final = "Para filtrar por registro indica también la tabla."


@dataclass(frozen=True)
class AuditFilters:
    """Filtros ya validados de `GET /audit` (todos opcionales; `None` no filtra)."""

    start: datetime | None = None
    end: datetime | None = None
    user_id: UUID | None = None
    table_name: str | None = None
    record_id: UUID | None = None
    subject_member_id: UUID | None = None
    action: str | None = None
    email_term: str | None = None


def build_audit_filters(query: AuditListQuery, page: PageParams, *, now: datetime) -> AuditFilters:
    """Pura: `AuditFilters` de la query o `AuditRangeInvalid` con el campo que falla."""
    if page.offset > MAX_AUDIT_OFFSET:
        raise AuditRangeInvalid(field="offset")
    try:
        check_instant_range(query.from_, query.to, now=now, field_start="from", field_end="to")
    except ValueError as error:
        raise AuditRangeInvalid(field=str(error.args[0])) from None
    if query.table is not None and query.table not in AUDITABLE_TABLES:
        raise AuditRangeInvalid(message=UNKNOWN_TABLE_MESSAGE, field="table")
    if query.record_id is not None and query.table is None:
        # S4A-D106 a: sin `table` el conteo no tiene índice líder; `(table_name, record_id)` sí.
        raise AuditRangeInvalid(message=RECORD_WITHOUT_TABLE_MESSAGE, field="record_id")
    q_record_id, email_term = _split_q(query.q)
    if query.record_id is not None or query.table is None:
        # S4A-D104 (ajustada por S4A-D106 a): el `record_id` explícito manda, y un `q` UUID
        # sin `table` no filtra.
        q_record_id = None
    return AuditFilters(
        start=query.from_,
        end=query.to,
        user_id=query.user_id,
        table_name=query.table,
        record_id=query.record_id if query.record_id is not None else q_record_id,
        subject_member_id=query.subject_member_id,
        action=query.action,
        email_term=email_term,
    )


def _split_q(q: str | None) -> tuple[UUID | None, str | None]:
    """`q` limpio: `(uuid, None)` si es un UUID, `(None, término)` si es otro texto y
    `(None, None)` si queda vacío."""
    termino = clean_query(q)
    if not termino:
        return None, None
    try:
        return UUID(termino), None
    except ValueError:
        return None, termino


def _conditions(filters: AuditFilters) -> builtins.list[ColumnElement[bool]]:
    """Igualdades y rango `[start, end)`; valores ligados, nunca texto SQL."""
    condiciones: builtins.list[ColumnElement[bool]] = []
    if filters.start is not None:
        condiciones.append(AuditEntry.at >= filters.start)
    if filters.end is not None:
        condiciones.append(AuditEntry.at < filters.end)
    iguales = (
        (AuditEntry.user_id, filters.user_id),
        (AuditEntry.table_name, filters.table_name),
        (AuditEntry.record_id, filters.record_id),
        (AuditEntry.subject_member_id, filters.subject_member_id),
        (AuditEntry.action, filters.action),
    )
    condiciones.extend(columna == valor for columna, valor in iguales if valor is not None)
    return condiciones


def _row(entrada: AuditEntry, refs: Mapping[UUID, UserRef]) -> dict[str, Any]:
    """Campos de `AuditRow`; correo y nombre `None` si el usuario no existe."""
    ref = refs.get(entrada.user_id)
    return {
        "seq": entrada.seq,
        "at": entrada.at,
        "user_id": entrada.user_id,
        "user_email": None if ref is None else ref.email,
        "user_name": None if ref is None else ref.display_name,
        "action": entrada.action,
        "table_name": entrada.table_name,
        "record_id": entrada.record_id,
        "subject_member_id": entrada.subject_member_id,
    }


async def list(  # nombre del contrato del plan B4 (las anotaciones usan builtins.list)
    session: AsyncSession, filters: AuditFilters, page: PageParams
) -> Page[AuditRow]:
    """Página de la auditoría, `seq` descendente (ver el docstring del módulo)."""
    condiciones = _conditions(filters)
    if filters.email_term is not None:
        ids = await auth_service.search_user_ids(session, filters.email_term)
        if not ids:
            return to_page([], 0, page)
        condiciones.append(AuditEntry.user_id == any_uuids(ids))
    consulta = select(AuditEntry).where(*condiciones).order_by(AuditEntry.seq.desc())
    # S4A-D106 b: el conteo recorre como mucho `MAX_AUDIT_OFFSET + 1` filas (leído al llamar).
    entradas, total = await paginate(session, consulta, page, count_limit=MAX_AUDIT_OFFSET + 1)
    refs = await auth_service.user_refs_for(session, [e.user_id for e in entradas])
    filas = [AuditRow.model_validate(_row(entrada, refs)) for entrada in entradas]
    return to_page(filas, total, page)


async def get(session: AsyncSession, seq: int) -> AuditDetail:
    """Detalle de la fila `seq` con el diff y sin blobs (ver el docstring del módulo)."""
    entrada = await session.scalar(select(AuditEntry).where(AuditEntry.seq == seq))
    if entrada is None:
        raise AuditEntryNotFound()
    refs = await auth_service.user_refs_for(session, [entrada.user_id])
    return AuditDetail.model_validate(
        {
            **_row(entrada, refs),
            "before": diff.redact_blobs(entrada.before),
            "after": diff.redact_blobs(entrada.after),
            "prev_hash": entrada.prev_hash,
            "hash": entrada.hash,
            "changes": diff.diff(entrada.before, entrada.after, entrada.action),
        }
    )


async def member_history(
    session: AsyncSession, member_id: UUID, page: PageParams, q: str | None
) -> Page[MemberHistoryItem]:
    """Historial del socio (S4A-B5, US-106; S4A-D20, S4A-D45, S4A-D54).

    `subject_member_id = member_id` por `seq DESC` (índice `ix_audit_log_subject_member_seq`) con
    `PageParams`; `page.offset > MAX_AUDIT_OFFSET` da `AuditRangeInvalid(field="offset")`. `q`
    (limpio con `clean_query`) filtra por quién actuó con
    `auth_service.search_user_ids(..., local_part_only=True)` (sin coincidencias, página vacía con
    `total = 0`; nunca por el dominio). Los nombres salen de `auth_service.user_names_for` (nunca
    `user_refs_for`: el coach no recibe correos); `fields` y `purpose` de `diff.history_fields` y
    `diff.history_purpose`. Solo lee: no escribe ni audita la lectura."""
    if page.offset > MAX_AUDIT_OFFSET:
        raise AuditRangeInvalid(field="offset")
    condiciones: builtins.list[ColumnElement[bool]] = [AuditEntry.subject_member_id == member_id]
    termino = clean_query(q)
    if termino:
        if DOMAIN_SEPARATOR in termino:
            # Revisión de B5 (LOW-1): la parte local nunca lleva `@`; ni se consulta.
            return to_page([], 0, page)
        ids = await auth_service.search_user_ids(session, termino, local_part_only=True)
        if not ids:
            return to_page([], 0, page)
        condiciones.append(AuditEntry.user_id == any_uuids(ids))
    consulta = select(AuditEntry).where(*condiciones).order_by(AuditEntry.seq.desc())
    # S4A-D106 b (duda 3 de B5): el mismo conteo acotado que `GET /audit` (leído al llamar).
    entradas, total = await paginate(session, consulta, page, count_limit=MAX_AUDIT_OFFSET + 1)
    nombres = await auth_service.user_names_for(session, [e.user_id for e in entradas])
    filas = [_history_item(entrada, nombres) for entrada in entradas]
    return to_page(filas, total, page)


def _history_item(entrada: AuditEntry, nombres: Mapping[UUID, str]) -> MemberHistoryItem:
    """Una fila del historial: nombre (nunca correo), nombres de campo y propósito."""
    return MemberHistoryItem(
        seq=entrada.seq,
        at=entrada.at,
        user_id=entrada.user_id,
        user_name=nombres.get(entrada.user_id),
        action=entrada.action,
        table_name=entrada.table_name,
        record_id=entrada.record_id,
        fields=diff.history_fields(entrada),
        purpose=diff.history_purpose(entrada),
    )


async def recent(
    session: AsyncSession,
    tables: Sequence[str],
    limit: int,
    *,
    actions: Sequence[AuditAction] = RECENT_ACTIONS,
    exclude_user_ids: Sequence[UUID] = (),
) -> builtins.list[AuditEntryView]:
    """Últimas filas reducidas de `tables` (S4A-D28, S4A-D51; ver el docstring del módulo)."""
    unicas = builtins.list(dict.fromkeys(tables))
    fuera = [tabla for tabla in unicas if tabla not in RECENT_TABLES_ALLOWED]
    if fuera:
        raise ValueError(f"recent: tablas fuera de la lista blanca: {fuera}")
    if not 1 <= limit <= MAX_RECENT_LIMIT:
        raise ValueError(f"recent: limit debe ir de 1 a {MAX_RECENT_LIMIT}")
    entradas: builtins.list[AuditEntry] = []
    for tabla in unicas:
        # S4A-D51: una sentencia por tabla (índice `ix_audit_log_table_seq`); valores ligados.
        condiciones: builtins.list[ColumnElement[bool]] = [
            AuditEntry.table_name == tabla,
            AuditEntry.action.in_(builtins.list(actions)),
        ]
        if exclude_user_ids:
            condiciones.append(AuditEntry.user_id != all_(uuid_array(exclude_user_ids)))
        consulta = (
            select(AuditEntry).where(*condiciones).order_by(AuditEntry.seq.desc()).limit(limit)
        )
        entradas.extend(await session.scalars(consulta))
    entradas.sort(key=lambda entrada: entrada.seq, reverse=True)
    return [diff.reduce_entry(entrada) for entrada in entradas[:limit]]
