"""Contrato de paginación (US-019; regla de datos 6, decisión D2).

- `PageParams`: `limit` (1..200, 25 por defecto) y `offset` (>= 0), como dependencia
  `Annotated[PageParams, Depends()]`. Un valor fuera de rango da 422 con el envelope de
  US-017 y `field = "limit"` u `"offset"`.
- `Page[T]`: `{items, total, limit, offset}` y nada más (`extra="forbid"`).
- `SearchQuery`: `q` de hasta 100 caracteres; nunca se registra en logs (US-018).
- `paginate(session, stmt, params)`: cuenta sobre la subconsulta y aplica `limit` y
  `offset` con orden estable: siempre agrega la clave primaria de la primera entidad
  como último criterio, así filas con la misma clave de orden no se repiten ni se omiten
  entre páginas. Solo recibe `select` de SQLAlchemy con parámetros ligados.

Cada `service.py` construye su `select` sobre sus propios `models` y llama a `paginate`;
nunca pagina `models` de otro módulo (regla de módulos 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Final

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LIMIT: Final = 25
MAX_LIMIT: Final = 200
MAX_SEARCH_LENGTH: Final = 100


@dataclass(frozen=True)
class PageParams:
    """Parámetros de página; FastAPI los lee de la query string al usarse con `Depends()`."""

    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT
    offset: Annotated[int, Query(ge=0)] = 0


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    limit: int
    offset: int


SearchQuery = Annotated[
    str | None,
    Query(max_length=MAX_SEARCH_LENGTH, description="Búsqueda libre; nunca se registra en logs"),
]


def _primary_key_columns(stmt: Select[Any]) -> list[Any]:
    """Columnas de la clave primaria de la primera entidad del `select`."""
    descripciones = stmt.column_descriptions
    if not descripciones:
        return []
    entidad = descripciones[0].get("entity")
    if entidad is None:
        return []
    mapper = inspect(entidad, raiseerr=False)
    if mapper is None:
        return []
    return list(mapper.primary_key)


def _with_stable_order(stmt: Select[Any]) -> Select[Any]:
    """Agrega la clave primaria al final del `ORDER BY` (o la usa sola si no hay)."""
    pk = _primary_key_columns(stmt)
    return stmt.order_by(*pk) if pk else stmt


async def paginate[T](
    session: AsyncSession, stmt: Select[T], params: PageParams
) -> tuple[list[T], int]:
    """`(items, total)` de una página. `total` respeta los filtros y no depende de la página."""
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    pagina = _with_stable_order(stmt).limit(params.limit).offset(params.offset)
    items = list((await session.execute(pagina)).scalars().all())
    return items, int(total or 0)


def to_page[T](items: Sequence[T], total: int, params: PageParams) -> Page[T]:
    return Page[T](items=list(items), total=total, limit=params.limit, offset=params.offset)
