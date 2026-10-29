"""Service del tablero (S4A-B8; US-108, US-110; S4A-D27, S4A-D28, S4A-D29).

Solo compone services: no tiene `models.py`, no importa `app.core.audit` ni ningún `models`, y
no ejecuta SQL (`tests/architecture/test_read_modules.py`).

- `month_of(today) -> "AAAA-MM"` (pura).
- `short_name(first_name, last_name) -> "Laura G."` (pura): nombre y la inicial del apellido.
- `format_cop(amount) -> "$ 120.000"` (pura): pesos con punto de miles.
- `movement_phrase(entry, names) -> str` (pura): la frase de una `AuditEntryView` con el
  catálogo de S4A-D28 (ver `MOVEMENT_PHRASES` en las pruebas). El actor va como `display_name`
  (parte local del correo o `Sistema`); si falta el socio o el plan se usa `GENERIC_MEMBER` o
  `GENERIC_PLAN` (nunca falla); el caso que el catálogo no cubre usa `ENTITY_LABELS`.
- `last_movements(session, *, with_finances)`: `audit.service.recent` con `MOVEMENT_TABLES`,
  `LAST_MOVEMENTS_LIMIT` y `exclude_user_ids=(SYSTEM_USER_ID,)`; nombres por lote con
  `members.service.names_for`, `memberships.service.refs_for` y `auth.service.user_names_for`.
- `summary(session, *, with_finances) -> DashboardOut`: `today_bogota()`, conteos de
  `memberships.service.summary(session, today=today)`, ingresos de
  `payments.service.summary(session, month_of(today)).total_cop` (solo con `with_finances`;
  si no, `None`) y `last_movements`. `can_see_finances(role)`: solo `FINANCE_ROLES` (S4A-D118:
  el coach no ve ingresos ni montos).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID
from app.core.security import Role

# Aristas de lectura del tablero (S4A-D27, C9): cinco services a nivel de módulo; nunca `plans`
# (el nombre del plan llega por `memberships.service.refs_for`) y nadie importa `dashboard`.
from app.modules.audit import service as audit_service
from app.modules.audit.schemas import AuditEntryView
from app.modules.auth import service as auth_service
from app.modules.dashboard.schemas import (
    LAST_MOVEMENTS_LIMIT,
    DashboardOut,
    MovementOut,
    MovementTable,
)
from app.modules.members import service as members_service
from app.modules.memberships import service as memberships_service
from app.modules.payments import service as payments_service

MOVEMENT_TABLES: Final[tuple[str, ...]] = (
    "members.members",
    "memberships.memberships",
    "payments.payments",
)
"""Las tres tablas de negocio de "últimos movimientos" (S4A-D28; nombres reales de la cadena)."""
GENERIC_MEMBER: Final = "un socio"
"""Socio cuyo nombre no se encontró (S4A-D28: la frase nunca falla)."""
GENERIC_PLAN: Final = "un plan"
"""Plan cuyo nombre no se encontró."""
ENTITY_LABELS: Final[Mapping[str, str]] = {
    "members.members": "la ficha",
    "memberships.memberships": "la membresía",
    "payments.payments": "el pago",
}
"""`{entidad}` de la frase genérica "modificó {entidad} de {Socio}" (S4A-D28)."""
GENERIC_ENTITY: Final = "un registro"
"""`{entidad}` de una tabla fuera de `ENTITY_LABELS` (no ocurre: `recent` solo lee las tres)."""
UNKNOWN_ACTOR: Final = "Alguien"
"""Actor cuyo usuario no existe (duda 2 del Rojo de B8; la frase nunca falla)."""
COVERAGE_PREFIX: Final = "La membresía "
"""Inicio de la activación por cobertura, la única frase sin actor (S4A-D28, US-110)."""
THOUSANDS_SEPARATOR: Final = "."
FINANCE_ROLES: Final[frozenset[str]] = frozenset({"admin"})
"""Roles que ven `income_month_cop` y los montos de las frases (S4A-D118; el coach no)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MovementNames:
    """Nombres por lote para `movement_phrase`: `actors` por `user_id` (`display_name`),
    `members` por `member_id` (ya en forma corta, `short_name`) y `plans` por id de membresía."""

    actors: Mapping[UUID, str] = field(default_factory=dict)
    members: Mapping[UUID, str] = field(default_factory=dict)
    plans: Mapping[UUID, str] = field(default_factory=dict)


def month_of(today: date) -> str:
    """El mes `AAAA-MM` de `today`."""
    return f"{today.year:04d}-{today.month:02d}"


def short_name(first_name: str, last_name: str) -> str:
    """`"Laura"`, `"Gómez Restrepo"` -> `"Laura G."`."""
    nombre, apellido = first_name.strip(), last_name.strip()
    if not apellido:
        return nombre
    return f"{nombre} {apellido[0]}."


def format_cop(amount: int) -> str:
    """`120000` -> `"$ 120.000"`."""
    return "$ " + f"{amount:,}".replace(",", THOUSANDS_SEPARATOR)


# Frases (S4A-D28): una función por tabla; `None` cae en la frase genérica -----------------


def _member_phrase(
    entry: AuditEntryView, socio: str, names: MovementNames, with_amount: bool
) -> str | None:
    """Fragmento de `members.members` sin el actor."""
    antes, despues = entry.before or {}, entry.after or {}
    if entry.action == "insert":
        return f"registró a {socio}"
    if entry.action != "update":
        return None
    if despues.get("deleted_at") is not None:
        return f"dio de baja a {socio}"
    if "deleted_at" in despues and antes.get("deleted_at") is not None:
        return f"reactivó a {socio}"
    return f"actualizó los datos de {socio}"


def _membership_phrase(
    entry: AuditEntryView, socio: str, names: MovementNames, with_amount: bool
) -> str | None:
    """Fragmento de `memberships.memberships`; la activación por cobertura empieza con
    `COVERAGE_PREFIX` y no lleva actor."""
    plan = names.plans.get(entry.record_id, GENERIC_PLAN) if entry.record_id else GENERIC_PLAN
    antes, despues = entry.before or {}, entry.after or {}
    if entry.action == "insert":
        return f"vendió {plan} a {socio}"
    if entry.action != "update":
        return None
    estado = despues.get("status")
    if estado == "cancelled":
        return f"anuló la membresía {plan} de {socio}"
    if antes.get("status") == "pending_payment" and estado not in (None, "pending_payment"):
        return f"{COVERAGE_PREFIX}{plan} de {socio} quedó al día"
    return f"actualizó la membresía {plan} de {socio}"


def _payment_phrase(
    entry: AuditEntryView, socio: str, names: MovementNames, with_amount: bool
) -> str | None:
    """Fragmento de `payments.payments`; el `insert` sin `amount_cop` entero es genérico. Sin
    `with_amount` (coach, S4A-D118) el registro no lleva el monto."""
    despues = entry.after or {}
    monto = despues.get("amount_cop")
    if entry.action == "insert" and isinstance(monto, int) and not isinstance(monto, bool):
        if not with_amount:
            return f"registró un pago de {socio}"
        return f"registró un pago de {format_cop(monto)} de {socio}"
    if entry.action == "update" and despues.get("voided") is True:
        return f"anuló un pago de {socio}"
    return None


_PhraseBuilder = Callable[[AuditEntryView, str, MovementNames, bool], str | None]
_PHRASES: Final[Mapping[str, _PhraseBuilder]] = {
    "members.members": _member_phrase,
    "memberships.memberships": _membership_phrase,
    "payments.payments": _payment_phrase,
}


def movement_phrase(
    entry: AuditEntryView, names: MovementNames, *, with_amount: bool = True
) -> str:
    """La frase de una entrada con el catálogo de S4A-D28 (ver el docstring del módulo); sin
    `with_amount` ninguna frase lleva montos (S4A-D118)."""
    actor = names.actors.get(entry.user_id, UNKNOWN_ACTOR)
    socio = GENERIC_MEMBER
    if entry.subject_member_id is not None:
        socio = names.members.get(entry.subject_member_id, GENERIC_MEMBER)
    armar = _PHRASES.get(entry.table_name)
    fragmento = None if armar is None else armar(entry, socio, names, with_amount)
    if fragmento is None:
        entidad = ENTITY_LABELS.get(entry.table_name, GENERIC_ENTITY)
        return f"{actor} modificó {entidad} de {socio}"
    if fragmento.startswith(COVERAGE_PREFIX):
        return fragmento
    return f"{actor} {fragmento}"


async def _names(session: AsyncSession, entries: Sequence[AuditEntryView]) -> MovementNames:
    """Los tres lotes de nombres (una lectura por service; S4A-D54: nunca correos)."""
    actores = await auth_service.user_names_for(session, [e.user_id for e in entries])
    socios = await members_service.names_for(
        session, (e.subject_member_id for e in entries if e.subject_member_id is not None)
    )
    membresias = [
        e.record_id
        for e in entries
        if e.table_name == "memberships.memberships" and e.record_id is not None
    ]
    refs = await memberships_service.refs_for(session, membresias)
    return MovementNames(
        actors=actores,
        members={i: short_name(n.first_name, n.last_name) for i, n in socios.items()},
        plans={i: ref.plan_name for i, ref in refs.items()},
    )


async def last_movements(session: AsyncSession, *, with_finances: bool) -> list[MovementOut]:
    """Las últimas `LAST_MOVEMENTS_LIMIT` frases sin el sistema, la más reciente primero; sin
    `with_finances` las frases de pagos no llevan monto (S4A-D118)."""
    entradas = await audit_service.recent(
        session, MOVEMENT_TABLES, LAST_MOVEMENTS_LIMIT, exclude_user_ids=(SYSTEM_USER_ID,)
    )
    if not entradas:
        return []
    nombres = await _names(session, entradas)
    return [
        MovementOut(
            seq=e.seq,
            at=e.at,
            phrase=movement_phrase(e, nombres, with_amount=with_finances),
            table_name=cast("MovementTable", e.table_name),
            record_id=e.record_id,
            member_id=e.subject_member_id,
        )
        for e in entradas
    ]


def can_see_finances(role: Role) -> bool:
    """S4A-D118: solo el admin ve ingresos y montos en el tablero (los pagos son de admin)."""
    return role in FINANCE_ROLES


async def summary(session: AsyncSession, *, with_finances: bool) -> DashboardOut:
    """El tablero completo (ver el docstring del módulo); sin `with_finances` (coach),
    `income_month_cop` es `None` y no se consulta, y las frases de pagos no llevan monto."""
    hoy = current_clock().today_bogota()
    membresias = await memberships_service.summary(session, today=hoy)
    mes = month_of(hoy)
    ingresos = None
    if with_finances:
        ingresos = (await payments_service.summary(session, mes)).total_cop
    return DashboardOut(
        today=hoy,
        members_active=membresias.active,
        members_expiring=membresias.expiring,
        members_expired=membresias.expired,
        members_frozen=membresias.frozen,
        members_pending_payment=membresias.pending_payment,
        income_month=mes,
        income_month_cop=ingresos,
        last_movements=await last_movements(session, with_finances=with_finances),
    )
