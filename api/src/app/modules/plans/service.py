"""Caso de uso de planes (S2-B9, US-078 y US-079; DECISIÓN 32, S2-D26, S2-D32).

Puras:
- `validate_plan(kind, duration_days, class_count)`: `days` no lleva `class_count`; `classes`
  exige `class_count` de 1 a 1.000; `duration_days` de 1 a 3.650. Lanza `PlanValidationError`
  con `field` y sin repetir el valor.
- `ensure_list_scope(role, active)`: el admin lista todo; el coach solo con `active=True`
  (S2-D26); cualquier otro caso (también `member`) da `PlanScopeForbidden`.
- `ensure_read_scope(role, plan)`: el admin lee todo; el coach solo planes activos; cualquier
  otro caso (también `member`) da `PlanScopeForbidden`.

Con sesión:
- `create(session, data)`: recorta el nombre, `validate_plan`, pre-chequea el nombre entre los
  vivos con `lower(btrim(name))`, inserta dentro de `begin_nested()` (la carrera la decide
  `uq_plans_name_alive` y su `IntegrityError` se traduce a `PlanNameDuplicated`; las fechas
  llegan con `eager_defaults`, M4) y emite `PlanCreated` en la misma transacción.
- `list(session, *, q, active, page, role)`: aplica `ensure_list_scope`; excluye los dados de
  baja; `q` sin tildes ni mayúsculas con `core.search.sql_fold` en columna y término (tabla
  completa desde la revisión Python H3), comodines escapados; `active` filtra; orden
  `name, id`; `paginate`.
- `detail(session, plan_id, *, role)`: lee el plan vivo (404 antes que el 403 del coach) y
  aplica `ensure_read_scope`; la respuesta de `GET /plans/{plan_id}`.
- Contratos para otros módulos: `get(session, plan_id, *, for_share=False)` (`PlanNotFound` si
  no existe o está dado de baja; `for_share` toma `FOR SHARE`), `get_including_deleted` y
  `names_for` (una consulta, incluye dados de baja).
- S3-B11 (D28): `search_ids(session, q)`: ids de planes vivos o dados de baja por nombre, con
  el pliegue de `list`; sin `q` da `set()` sin consultar.

S4A-B7 (US-080, US-081, US-082; S4A-D22 a D26, D60, D72):
- `merge_plan(current, patch) -> PlanState` (pura): aplica solo lo enviado
  (`model_fields_set`); pasar a `days` desde `classes` exige `class_count: null` explícito
  (si no, `PlanValidationError` con `field="class_count"`); luego `validate_plan`.
- `update(session, plan_id, patch) -> PlanOut`: `FOR UPDATE` del plan vivo (`PlanNotFound`),
  `merge_plan`, pre-chequeo del nombre y traducción de `uq_plans_name_alive` a
  `PlanNameDuplicated`; sin cambios no hay `flush`, auditoría ni evento; con cambios,
  `PlanUpdated(plan_id, changed_fields)` (nombres, nunca valores).
- `set_active(session, plan_id, active) -> PlanOut`: idempotente; desactivar emite
  `PlanDeactivated`, activar `PlanUpdated(changed_fields=("is_active",))`.
- `deactivate_or_fail(session, plan_id) -> None`: `FOR UPDATE` del plan vivo, cuenta las
  membresías activas por la perezosa `plans -> memberships` (G-03; `count_active_by_plan`) y
  da `PlanHasActiveMemberships(count)` o la baja (`deleted_at` e `is_active` falso en un solo
  `flush`; `PlanDeactivated` solo si estaba activo).
- `_out_with_counts(session, planes)`: `PlanOut` con `active_members_count` de
  `memberships.service.counts_active_by_plans` (perezosa, G-03) en `list`, `detail`, `update`
  y `set_active`; `create` devuelve 0 sin consultar.
"""

from __future__ import annotations

import builtins
import logging
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Row, Text, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core import events
from app.core.clock import current_clock
from app.core.context import get_actor
from app.core.db import violated_constraint
from app.core.events import DomainEvent
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.core.security import Role
from app.modules.plans.exceptions import (
    PlanHasActiveMemberships,
    PlanNameDuplicated,
    PlanNotFound,
    PlanScopeForbidden,
    PlanValidationError,
)
from app.modules.plans.models import KINDS, NAME_ALIVE_INDEX, Plan
from app.modules.plans.schemas import (
    CLASS_COUNT_MAX,
    CLASS_COUNT_MIN,
    DURATION_DAYS_MAX,
    DURATION_DAYS_MIN,
    PlanCreate,
    PlanOut,
    PlanPatch,
    PlanSnapshot,
    PlanState,
)

logger = logging.getLogger("app.plans")

type _Texto = ColumnElement[str] | InstrumentedAttribute[str]


_MENSAJES: Final[Mapping[str, str]] = {
    "kind": "El tipo de plan debe ser days o classes.",
    "duration_days": "La duración debe estar entre 1 y 3.650 días.",
    "class_count_days": "Un plan por días no lleva número de clases.",
    "class_count_classes": "Un plan por clases necesita entre 1 y 1.000 clases.",
    "obligatorio": "Este campo no puede quedar vacío.",
}

_CAMPOS_EDITABLES: Final[tuple[str, ...]] = (
    "class_count",
    "duration_days",
    "kind",
    "name",
    "price_cop",
)
"""Las columnas que `PATCH` puede cambiar, en orden alfabético (`PlanUpdated.changed_fields`)."""

_OBLIGATORIOS: Final[frozenset[str]] = frozenset({"duration_days", "kind", "name", "price_cop"})
"""Las que no admiten `null` explícito en el `PATCH` (solo `class_count` es anulable)."""


@dataclass(frozen=True, kw_only=True)
class PlanCreated(DomainEvent):
    plan_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanUpdated(DomainEvent):
    """S4A-D22, D23: `changed_fields` son nombres de columna en orden alfabético, nunca valores."""

    plan_id: UUID
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanDeactivated(DomainEvent):
    """S4A-D23, D24: el plan dejó de estar activo (desactivado o dado de baja estando activo)."""

    plan_id: UUID


# Reglas puras --------------------------------------------------------------------------


def _invalido(campo: str, clave: str | None = None) -> PlanValidationError:
    """422 con `field`; el mensaje nunca repite el valor recibido."""
    return PlanValidationError(message=_MENSAJES[clave or campo], field=campo)


def validate_plan(kind: str, duration_days: int, class_count: int | None) -> None:
    """Regla que cruza `kind` y `class_count` (US-078); `PlanValidationError` con `field`."""
    if kind not in KINDS:
        raise _invalido("kind")
    if not DURATION_DAYS_MIN <= duration_days <= DURATION_DAYS_MAX:
        raise _invalido("duration_days")
    if kind == "days":
        if class_count is not None:
            raise _invalido("class_count", "class_count_days")
        return
    if class_count is None or not CLASS_COUNT_MIN <= class_count <= CLASS_COUNT_MAX:
        raise _invalido("class_count", "class_count_classes")


def ensure_list_scope(role: Role, active: bool | None) -> None:
    """S2-D26: el admin lista todo; el coach solo con `active=True`."""
    if role == "admin":
        return
    if role == "coach" and active is True:
        return
    raise PlanScopeForbidden()


def ensure_read_scope(role: Role, plan: PlanSnapshot) -> None:
    """S2-D26: el admin lee todo; el coach solo planes activos."""
    if role == "admin":
        return
    if role == "coach" and plan.is_active:
        return
    raise PlanScopeForbidden()


# Lecturas comunes ------------------------------------------------------------------------


def _nombre_normalizado(valor: _Texto) -> ColumnElement[str]:
    """La forma que compara `uq_plans_name_alive`: `lower(btrim(...))`."""
    return func.lower(func.btrim(valor))


def _vivo() -> ColumnElement[bool]:
    return Plan.deleted_at.is_(None)


def _out(plan: Plan, active_members_count: int = 0) -> PlanOut:
    return PlanOut.model_validate(
        {
            "id": plan.id,
            "name": plan.name,
            "price_cop": plan.price_cop,
            "kind": plan.kind,
            "duration_days": plan.duration_days,
            "class_count": plan.class_count,
            "is_active": plan.is_active,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "active_members_count": active_members_count,
        }
    )


_COLUMNAS_SNAPSHOT: Final = (
    Plan.id,
    Plan.name,
    Plan.price_cop,
    Plan.kind,
    Plan.duration_days,
    Plan.class_count,
    Plan.is_active,
    Plan.deleted_at,
)


def _snapshot(fila: Plan | Row[*tuple[Any, ...]]) -> PlanSnapshot:
    """El contrato para otros módulos desde el ORM o desde una fila de `_COLUMNAS_SNAPSHOT`."""
    return PlanSnapshot(
        id=fila.id,
        name=fila.name,
        price_cop=fila.price_cop,
        kind=fila.kind,
        duration_days=fila.duration_days,
        class_count=fila.class_count,
        is_active=fila.is_active,
        deleted_at=fila.deleted_at,
    )


async def _id_por_nombre(
    session: AsyncSession, nombre: str, *, excepto: UUID | None = None
) -> UUID | None:
    """Id del plan vivo con ese nombre sin distinguir mayúsculas ni espacios de los extremos;
    `excepto` excluye el propio plan al renombrar (S4A-D22)."""
    termino = _nombre_normalizado(literal(nombre, Text))  # valor ligado
    consulta = select(Plan.id).where(_nombre_normalizado(Plan.name) == termino, _vivo())
    if excepto is not None:
        consulta = consulta.where(Plan.id != excepto)
    resultado: UUID | None = await session.scalar(consulta)
    return resultado


# Alta, lista y detalle ------------------------------------------------------------------


async def _insert(session: AsyncSession, plan: Plan) -> None:
    """La carrera la decide `uq_plans_name_alive` dentro de un savepoint."""
    try:
        async with session.begin_nested():
            session.add(plan)
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != NAME_ALIVE_INDEX:
            raise
        logger.info("plans: alta concurrente con el mismo nombre")
        raise PlanNameDuplicated(await _id_por_nombre(session, plan.name)) from None


async def create(session: AsyncSession, data: PlanCreate) -> PlanOut:
    """Alta de un plan (US-078): nombre en NFC, `validate_plan`, único entre vivos y
    `PlanCreated` en la misma transacción."""
    nombre = unicodedata.normalize("NFC", data.name).strip()
    validate_plan(data.kind, data.duration_days, data.class_count)
    existente = await _id_por_nombre(session, nombre)
    if existente is not None:
        raise PlanNameDuplicated(existente)
    plan = Plan(
        name=nombre,
        price_cop=data.price_cop,
        kind=data.kind,
        duration_days=data.duration_days,
        class_count=data.class_count,
        is_active=True,
        created_by=get_actor(),
    )
    await _insert(session, plan)  # `eager_defaults`: fechas ya cargadas (M4)
    await events.emit(PlanCreated(plan_id=plan.id), session)
    logger.info("plans: plan creado", extra={"plan_id": str(plan.id)})
    return _out(plan)


async def list(  # nombre del contrato del blueprint B9 (las anotaciones usan builtins.list)
    session: AsyncSession,
    *,
    q: str | None,
    active: bool | None,
    page: PageParams,
    role: Role,
) -> Page[PlanOut]:
    """US-079: la página de planes vivos con `q` y `active`."""
    ensure_list_scope(role, active)
    consulta = select(Plan).where(_vivo())
    if active is not None:
        consulta = consulta.where(Plan.is_active == active)
    termino = clean_query(q)  # core/search (H3)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(sql_fold(Plan.name).ilike(patron, escape=LIKE_ESCAPE))
    planes, total = await paginate(session, consulta.order_by(Plan.name), page)
    return to_page(await _out_with_counts(session, planes), total, page)


async def detail(session: AsyncSession, plan_id: UUID, *, role: Role) -> PlanOut:
    """`GET /plans/{plan_id}`: 404 si no está vivo (antes que el 403 del coach)."""
    plan = await session.scalar(select(Plan).where(Plan.id == plan_id, _vivo()))
    if plan is None:
        raise PlanNotFound()
    ensure_read_scope(role, _snapshot(plan))
    return await _out_one(session, plan)


# Editar, activar o desactivar y dar de baja (S4A-B7) ---------------------------------------


def merge_plan(current: PlanSnapshot, patch: PlanPatch) -> PlanState:
    """S4A-D22: el plan resultante de aplicar lo enviado en `patch` (docstring del módulo).

    Pasar a `classes` sin `class_count`, o a `days` sin `class_count: null` explícito, deja un
    plan que `validate_plan` rechaza con `field="class_count"`."""
    valores: dict[str, Any] = {campo: getattr(current, campo) for campo in _CAMPOS_EDITABLES}
    for campo in patch.model_fields_set & set(_CAMPOS_EDITABLES):
        valor = getattr(patch, campo)
        if valor is None and campo in _OBLIGATORIOS:
            raise _invalido(campo, "obligatorio")
        valores[campo] = valor
    valores["name"] = unicodedata.normalize("NFC", valores["name"]).strip()
    validate_plan(valores["kind"], valores["duration_days"], valores["class_count"])
    return PlanState(**valores)


def _cambios(plan: Plan, estado: PlanState) -> builtins.list[str]:
    """Columnas cuyo valor cambia, en orden alfabético."""
    return [c for c in _CAMPOS_EDITABLES if getattr(plan, c) != getattr(estado, c)]


async def _out_with_counts(session: AsyncSession, planes: Iterable[Plan]) -> builtins.list[PlanOut]:
    """S4A-D25: `PlanOut` con `active_members_count` por lote: una consulta a `memberships` por
    página (ninguna sin planes)."""
    lista = builtins.list(planes)
    if not lista:
        return []
    # lazy: G-03 (plans -> memberships)
    from app.modules.memberships import service as memberships_service

    conteos = await memberships_service.counts_active_by_plans(session, [p.id for p in lista])
    return [_out(plan, conteos.get(plan.id, 0)) for plan in lista]


async def _out_one(session: AsyncSession, plan: Plan) -> PlanOut:
    (salida,) = await _out_with_counts(session, [plan])
    return salida


async def _bloquear(session: AsyncSession, plan_id: UUID) -> Plan:
    """El plan vivo con `FOR UPDATE`, recargado (`populate_existing`) o `PlanNotFound`."""
    consulta = (
        select(Plan)
        .where(Plan.id == plan_id, _vivo())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    plan = await session.scalar(consulta)
    if plan is None:
        raise PlanNotFound()
    return plan


async def _guardar(
    session: AsyncSession, plan: Plan, estado: PlanState, cambios: builtins.list[str]
) -> None:
    """Asigna solo las columnas que cambian y hace un `flush` en un savepoint; la carrera de
    nombres la decide `uq_plans_name_alive` y se traduce a `PlanNameDuplicated`."""
    plan_id = plan.id  # el rollback del savepoint expira `plan`
    try:
        async with session.begin_nested():
            for campo in cambios:
                setattr(plan, campo, getattr(estado, campo))
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != NAME_ALIVE_INDEX:
            raise
        logger.info("plans: renombre concurrente con el mismo nombre")
        ganador = await _id_por_nombre(session, estado.name, excepto=plan_id)
        raise PlanNameDuplicated(ganador) from None


async def update(session: AsyncSession, plan_id: UUID, patch: PlanPatch) -> PlanOut:
    """US-080 (S4A-D22): edita el plan vivo (docstring del módulo). Sin cambios efectivos no hay
    `flush`, auditoría ni evento."""
    plan = await _bloquear(session, plan_id)
    estado = merge_plan(_snapshot(plan), patch)
    cambios = _cambios(plan, estado)
    if not cambios:
        return await _out_one(session, plan)
    if "name" in cambios:
        existente = await _id_por_nombre(session, estado.name, excepto=plan_id)
        if existente is not None:
            raise PlanNameDuplicated(existente)
    await _guardar(session, plan, estado, cambios)
    await events.emit(PlanUpdated(plan_id=plan_id, changed_fields=tuple(cambios)), session)
    logger.info("plans: plan editado", extra={"plan_id": str(plan_id), "plan_fields": cambios})
    return await _out_one(session, plan)


async def set_active(session: AsyncSession, plan_id: UUID, active: bool) -> PlanOut:
    """US-081 (S4A-D23): activa o desactiva el plan vivo, idempotente. Desactivar emite
    `PlanDeactivated`; activar, `PlanUpdated(changed_fields=("is_active",))`."""
    plan = await _bloquear(session, plan_id)
    if plan.is_active != active:
        plan.is_active = active
        await session.flush()
        evento: DomainEvent = (
            PlanUpdated(plan_id=plan_id, changed_fields=("is_active",))
            if active
            else PlanDeactivated(plan_id=plan_id)
        )
        await events.emit(evento, session)
        logger.info("plans: plan activado o desactivado", extra={"plan_id": str(plan_id)})
    return await _out_one(session, plan)


async def deactivate_or_fail(session: AsyncSession, plan_id: UUID) -> None:
    """US-082 (S4A-D24): baja lógica (`deleted_at` del reloj e `is_active` falso en un solo
    `flush`) o `PlanHasActiveMemberships(count)` con el plan intacto."""
    plan = await _bloquear(session, plan_id)
    # lazy: G-03 (plans -> memberships)
    from app.modules.memberships import service as memberships_service

    activas = await memberships_service.count_active_by_plan(session, plan_id)
    if activas > 0:
        raise PlanHasActiveMemberships(activas)
    estaba_activo = plan.is_active
    plan.deleted_at = current_clock().now_utc()
    if estaba_activo:
        plan.is_active = False
    await session.flush()
    if estaba_activo:
        await events.emit(PlanDeactivated(plan_id=plan_id), session)
    logger.info("plans: plan dado de baja", extra={"plan_id": str(plan_id)})


# Contratos para otros módulos -----------------------------------------------------------


async def get(session: AsyncSession, plan_id: UUID, *, for_share: bool = False) -> PlanSnapshot:
    """Contrato para otros módulos: el plan vivo (`FOR SHARE` opcional) o `PlanNotFound`."""
    consulta = select(*_COLUMNAS_SNAPSHOT).where(Plan.id == plan_id, _vivo())
    if for_share:
        consulta = consulta.with_for_update(read=True)
    fila = (await session.execute(consulta)).first()
    if fila is None:
        raise PlanNotFound()
    return _snapshot(fila)


async def get_including_deleted(session: AsyncSession, plan_id: UUID) -> PlanSnapshot:
    """Como `get`, también dados de baja."""
    consulta = select(*_COLUMNAS_SNAPSHOT).where(Plan.id == plan_id)
    fila = (await session.execute(consulta)).first()
    if fila is None:
        raise PlanNotFound()
    return _snapshot(fila)


async def names_for(session: AsyncSession, plan_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Nombre de cada id existente, incluidos los dados de baja, en una consulta."""
    buscados = builtins.list(dict.fromkeys(plan_ids))
    if not buscados:
        return {}
    consulta = select(Plan.id, Plan.name).where(Plan.id.in_(buscados))
    return {fila.id: fila.name for fila in await session.execute(consulta)}


async def search_ids(session: AsyncSession, q: str | None) -> set[UUID]:
    """S3-B11 (D28): ids de los planes (vivos o dados de baja) cuyo nombre contiene `q`, con el
    mismo pliegue de tildes y mayúsculas de `list` (`core.search`); `q` vacío o en blanco da
    `set()` sin consultar. Lo usa la pestaña de membresías de la ficha para su `q`."""
    termino = clean_query(q)  # core/search (H3), como `list`
    if not termino:
        return set()
    patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
    consulta = select(Plan.id).where(sql_fold(Plan.name).ilike(patron, escape=LIKE_ESCAPE))
    return set((await session.scalars(consulta)).all())


__all__: builtins.list[str] = [
    "PlanCreated",
    "PlanDeactivated",
    "PlanUpdated",
    "create",
    "deactivate_or_fail",
    "detail",
    "ensure_list_scope",
    "ensure_read_scope",
    "get",
    "get_including_deleted",
    "list",
    "merge_plan",
    "names_for",
    "search_ids",
    "set_active",
    "update",
    "validate_plan",
]
