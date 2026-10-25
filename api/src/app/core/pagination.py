"""Contrato de paginación (US-019; regla de datos 6, decisión D2).

- `PageParams`: `limit` (1..200, 25 por defecto) y `offset` (0..`MAX_OFFSET`), como dependencia
  `Annotated[PageParams, Depends()]`. Un valor fuera de rango da 422 con el envelope de
  US-017 y `field = "limit"` u `"offset"`. `MAX_OFFSET` (un millón) existe porque un entero
  fuera de int64 llegaba a PostgreSQL y daba 500 (revisión de seguridad V10, N-2).
- `Page[T]`: `{items, total, limit, offset}` y nada más (`extra="forbid"`).
- `SearchQuery`: `q` de hasta 100 caracteres y sin caracteres de control (categoría `Cc`:
  U+0000 a U+001F y U+007F a U+009F). Un NUL lo rechaza PostgreSQL como parámetro y daba 500
  (revisión S2-B8, MEDIUM-1; cerrado en S2-B9): un valor fuera de contrato da 422 con
  `field = "q"` en todas las listas, antes de cualquier service. Nunca se registra en logs
  (US-018).
- `uuid_array(ids)` y `any_uuids(ids)` (PM4 de la revisión de Fase 4 del Sprint 3): un solo
  parámetro ligado de tipo `uuid[]` con los ids ordenados (S3-D60) y `= ANY(...)` sobre él; la
  única copia (antes había una en `memberships`, otra en `members` y un literal en `payments`).
- `paginate(session, stmt, params)`: cuenta sobre la subconsulta y aplica `limit` y
  `offset` con orden estable: siempre agrega la clave primaria de la primera entidad
  como último criterio, así filas con la misma clave de orden no se repiten ni se omiten
  entre páginas. Solo recibe `select` de SQLAlchemy con parámetros ligados.

Cada `service.py` construye su `select` sobre sus propios `models` y llama a `paginate`;
nunca pagina `models` de otro módulo (regla de módulos 2).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import ColumnElement, Select, Uuid, any_, func, inspect, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LIMIT: Final = 25
MAX_LIMIT: Final = 200
MAX_SEARCH_LENGTH: Final = 100
MAX_OFFSET: Final = 1_000_000
# Tamaño de lote de ids para `= ANY(:ids)` en consultas entre módulos (S3-D59, D-5).
ID_BATCH: Final = 200
# Sin caracteres de control (categoría Unicode `Cc`). Con escapes, para que el patrón publicado
# en el OpenAPI sea texto imprimible.
SEARCH_PATTERN: Final = r"^[^\x00-\x1f\x7f-\x9f]*$"


@dataclass(frozen=True)
class PageParams:
    """Parámetros de página; FastAPI los lee de la query string al usarse con `Depends()`."""

    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    limit: int
    offset: int


SearchQuery = Annotated[
    str | None,
    Query(
        max_length=MAX_SEARCH_LENGTH,
        pattern=SEARCH_PATTERN,
        description="Búsqueda libre sin caracteres de control; nunca se registra en logs",
    ),
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


def chunked[T](items: Sequence[T], size: int = ID_BATCH) -> Iterator[Sequence[T]]:
    """Lotes consecutivos de `items` de a `size` (el último puede ser menor), en orden.

    `ValueError` con `size <= 0` (sin el control, `size=0` sería un bucle infinito)."""
    if size <= 0:
        raise ValueError(f"chunked exige size > 0 (size={size})")
    return (items[inicio : inicio + size] for inicio in range(0, len(items), size))


def uuid_array(ids: Iterable[UUID]) -> ColumnElement[Any]:
    """Los ids como UN parámetro ligado `uuid[]`, ordenados (S3-D60; para `ANY` o `ALL`)."""
    return literal(sorted(ids), ARRAY(Uuid()))


def any_uuids(ids: Iterable[UUID]) -> ColumnElement[Any]:
    """`= ANY(:ids)` con un solo parámetro de tipo `uuid[]` (S3-D60)."""
    return any_(uuid_array(ids))
