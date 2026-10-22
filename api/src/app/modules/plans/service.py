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
from app.core.context import get_actor
from app.core.db import violated_constraint
from app.core.events import DomainEvent
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.core.security import Role
from app.modules.plans.exceptions import (
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
    PlanSnapshot,
)

logger = logging.getLogger("app.plans")

type _Texto = ColumnElement[str] | InstrumentedAttribute[str]


_MENSAJES: Final[Mapping[str, str]] = {
    "kind": "El tipo de plan debe ser days o classes.",
    "duration_days": "La duración debe estar entre 1 y 3.650 días.",
    "class_count_days": "Un plan por días no lleva número de clases.",
    "class_count_classes": "Un plan por clases necesita entre 1 y 1.000 clases.",
}


@dataclass(frozen=True, kw_only=True)
class PlanCreated(DomainEvent):
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


def _out(plan: Plan) -> PlanOut:
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


async def _id_por_nombre(session: AsyncSession, nombre: str) -> UUID | None:
    """Id del plan vivo con ese nombre sin distinguir mayúsculas ni espacios de los extremos."""
    termino = _nombre_normalizado(literal(nombre, Text))  # valor ligado
    consulta = select(Plan.id).where(_nombre_normalizado(Plan.name) == termino, _vivo())
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
    return to_page([_out(p) for p in planes], total, page)


async def detail(session: AsyncSession, plan_id: UUID, *, role: Role) -> PlanOut:
    """`GET /plans/{plan_id}`: 404 si no está vivo (antes que el 403 del coach)."""
    plan = await session.scalar(select(Plan).where(Plan.id == plan_id, _vivo()))
    if plan is None:
        raise PlanNotFound()
    ensure_read_scope(role, _snapshot(plan))
    return _out(plan)


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


__all__: builtins.list[str] = [
    "PlanCreated",
    "create",
    "detail",
    "ensure_list_scope",
    "ensure_read_scope",
    "get",
    "get_including_deleted",
    "list",
    "names_for",
    "validate_plan",
]
