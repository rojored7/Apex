"""Catálogo de movimientos (S8-A1, US-165; S8-D5). Privado del módulo: se usa por `service.py`.

- `create_movement(session, data, by)`: normaliza el nombre (`rules`), rechaza el
  repetido con 409 `movement_exists` (`field = "name"`, `existing_id`) y guarda activo. La carrera
  de dos altas la decide `uq_movements_name_norm` dentro de un savepoint.
- `update_movement(session, movement_id, patch, by)`: `FOR UPDATE` de la fila, aplica
  solo lo enviado (`model_fields_set`; `null` explícito da 422 con `field`) y vuelve a comprobar el
  nombre contra los demás. Sin cambios no hay `flush` ni auditoría.
- `get_movement` y `list_movements(session, filters, page, q=)`: la lista ordena por nombre
  normalizado y pide `usage_counts` UNA vez por página.
No hay borrado: se desactivan con `is_active = false` (RN-14; los triggers también lo prohíben).
"""

from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Text, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import violated_constraint
from app.core.pagination import Page, PageParams, paginate, to_page
from app.core.search import LIKE_ESCAPE, clean_query, contains_pattern, sql_fold
from app.modules.wods.exceptions import MovementExists, MovementNotFound, WodsValidationError
from app.modules.wods.models import Movement
from app.modules.wods.rules import clean_movement_name, normalize_movement_name
from app.modules.wods.schemas import (
    CatalogMovementOut,
    MovementCreate,
    MovementListQuery,
    MovementPatch,
)

logger = logging.getLogger("app.wods")

UQ_NAME_NORM: Final = "uq_movements_name_norm"
_EDITABLES: Final[tuple[str, ...]] = ("name", "category", "unit", "is_active")
_MENSAJE_NULO: Final = "Este campo no puede quedar vacío."


async def usage_counts(session: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
    """WODs que usan cada movimiento. En A1 no hay WODs: todos en 0 (A3 la reemplaza por la
    consulta agrupada sobre `wod_movements`, una por página)."""
    return dict.fromkeys(ids, 0)


def _out(mov: Movement, usos: dict[UUID, int]) -> CatalogMovementOut:
    return CatalogMovementOut.model_validate(
        {
            "id": mov.id,
            "name": mov.name,
            "category": mov.category,
            "unit": mov.unit,
            "is_active": mov.is_active,
            "wod_count": usos.get(mov.id, 0),
            "created_at": mov.created_at,
            "updated_at": mov.updated_at,
        }
    )


async def _outs(session: AsyncSession, movs: list[Movement]) -> list[CatalogMovementOut]:
    """`CatalogMovementOut` de cada movimiento con los conteos de la página en una sola llamada."""
    usos = await usage_counts(session, [m.id for m in movs]) if movs else {}
    return [_out(m, usos) for m in movs]


async def _id_by_norm(session: AsyncSession, norm: str, *, exclude: UUID | None) -> UUID | None:
    consulta = select(Movement.id).where(Movement.name_norm == norm)
    if exclude is not None:
        consulta = consulta.where(Movement.id != exclude)
    return await session.scalar(consulta)


async def _flush_unico(session: AsyncSession, norm: str, exclude: UUID | None) -> None:
    """`flush` en un savepoint: el 23505 del índice único es 409 `movement_exists`."""
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as error:
        if violated_constraint(error) != UQ_NAME_NORM:
            raise
        raise MovementExists(await _id_by_norm(session, norm, exclude=exclude)) from None


async def create_movement(
    session: AsyncSession, data: MovementCreate, by: UUID
) -> CatalogMovementOut:
    """Alta de un movimiento activo (US-165 CA1, CA2)."""
    norm = normalize_movement_name(data.name)
    existente = await _id_by_norm(session, norm, exclude=None)
    if existente is not None:
        raise MovementExists(existente)
    mov = Movement(
        name=clean_movement_name(data.name),
        name_norm=norm,
        category=data.category,
        unit=data.unit,
        is_active=True,
        created_by=by,
    )
    session.add(mov)
    await _flush_unico(session, norm, None)  # `eager_defaults`: fechas ya cargadas
    logger.info("wods: movimiento creado", extra={"movement_id": str(mov.id)})
    return (await _outs(session, [mov]))[0]


async def _locked(session: AsyncSession, movement_id: UUID) -> Movement:
    mov = await session.scalar(
        select(Movement)
        .where(Movement.id == movement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if mov is None:
        raise MovementNotFound()
    return mov


async def update_movement(
    session: AsyncSession, movement_id: UUID, patch: MovementPatch, by: UUID
) -> CatalogMovementOut:
    """`PATCH` de un movimiento (US-165 CA5): solo lo enviado; ningún campo admite `null`."""
    mov = await _locked(session, movement_id)
    valores: dict[str, Any] = {}
    for campo in patch.model_fields_set & set(_EDITABLES):
        valor = getattr(patch, campo)
        if valor is None:
            raise WodsValidationError(message=_MENSAJE_NULO, field=campo)
        valores[campo] = clean_movement_name(valor) if campo == "name" else valor
    cambios = {c: v for c, v in valores.items() if getattr(mov, c) != v}
    if not cambios:
        return (await _outs(session, [mov]))[0]
    norm = mov.name_norm
    if "name" in cambios:
        norm = normalize_movement_name(cambios["name"])
        otro = await _id_by_norm(session, norm, exclude=mov.id)
        if otro is not None:
            raise MovementExists(otro)
        mov.name_norm = norm
    for campo, valor in cambios.items():
        setattr(mov, campo, valor)
    await _flush_unico(session, norm, mov.id)
    logger.info(
        "wods: movimiento editado",
        extra={"movement_id": str(mov.id), "changed_fields": sorted(cambios), "actor": str(by)},
    )
    return (await _outs(session, [mov]))[0]


async def get_movement(session: AsyncSession, movement_id: UUID) -> CatalogMovementOut:
    mov = await session.get(Movement, movement_id)
    if mov is None:
        raise MovementNotFound()
    return (await _outs(session, [mov]))[0]


async def list_movements(
    session: AsyncSession, filters: MovementListQuery, page: PageParams, *, q: str | None = None
) -> Page[CatalogMovementOut]:
    """`GET /movements`: `q` (nombre, sin tildes ni mayúsculas), `category` y `active`; orden por
    nombre normalizado."""
    consulta = select(Movement)
    termino = clean_query(q)
    if termino:
        patron = sql_fold(literal(contains_pattern(termino), Text))  # valor ligado
        consulta = consulta.where(sql_fold(Movement.name).ilike(patron, escape=LIKE_ESCAPE))
    if filters.category is not None:
        consulta = consulta.where(Movement.category == filters.category)
    if filters.active is not None:
        consulta = consulta.where(Movement.is_active.is_(filters.active))
    movs, total = await paginate(session, consulta.order_by(Movement.name_norm, Movement.id), page)
    return to_page(await _outs(session, movs), total, page)
