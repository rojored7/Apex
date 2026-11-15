"""Router de `wods` (S8-A1, US-165). Plano, con la ruta completa en el decorador (S2-D3).

Movimientos, admin y coach (`StaffDep`; el socio recibe 403):
- `GET /movements`: `Page[CatalogMovementOut]` con `PageParams`, `q`, `category` y `active`;
  `staff-read`. Códigos 200, 401, 403, 422 y 429.
- `POST /movements`: 201 `CatalogMovementOut`; `wods-write` (30 por minuto por usuario). Códigos
  201, 401, 403, 409, 422 y 429.
- `PATCH /movements/{movement_id}`: `CatalogMovementOut`; `wods-write`. Códigos 200, 401, 403, 404,
  409, 422 y 429. No existe `DELETE`: se desactivan con `is_active`.
Benchmarks (S8-A2, US-166, S8-D6), mismo reparto de roles y cubetas:
- `GET /benchmarks`: `Page[BenchmarkOut]` con `PageParams`, `q` y `score_type`; `staff-read`.
  Códigos 200, 401, 403, 422 y 429.
- `POST /benchmarks`: 201 `BenchmarkOut`; `wods-write`. Códigos 201, 401, 403, 409, 422 y 429.
- `PATCH /benchmarks/{benchmark_id}`: `BenchmarkOut`; `wods-write`. Códigos 200, 401, 403, 404, 409,
  422 (incluye `score_type_locked`) y 429. Tampoco existe `DELETE`.
Las rutas no hacen `select`: validan, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import StaffDep
from app.modules.wods import service
from app.modules.wods.schemas import (
    BenchmarkCreate,
    BenchmarkListQuery,
    BenchmarkOut,
    BenchmarkPatch,
    CatalogMovementOut,
    MovementCreate,
    MovementListQuery,
    MovementPatch,
)

router = APIRouter(
    tags=["wods"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.get(
    "/movements", response_model=Page[CatalogMovementOut], responses=responses_for(422, 429)
)
async def list_movements(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    filters: Annotated[MovementListQuery, Depends()],
    q: SearchQuery = None,
) -> Page[CatalogMovementOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_movements(session, filters, page, q=q)


@router.post(
    "/movements",
    status_code=201,
    response_model=CatalogMovementOut,
    responses=responses_for(409, 422, 429),
)
async def create_movement(
    request: Request, body: MovementCreate, principal: StaffDep, session: Session
) -> CatalogMovementOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.create_movement(session, body, principal.user_id)


@router.patch(
    "/movements/{movement_id}",
    response_model=CatalogMovementOut,
    responses=responses_for(404, 409, 422, 429),
)
async def update_movement(
    request: Request,
    movement_id: UUID,
    body: MovementPatch,
    principal: StaffDep,
    session: Session,
) -> CatalogMovementOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.update_movement(session, movement_id, body, principal.user_id)


@router.get("/benchmarks", response_model=Page[BenchmarkOut], responses=responses_for(422, 429))
async def list_benchmarks(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    filters: Annotated[BenchmarkListQuery, Depends()],
    q: SearchQuery = None,
) -> Page[BenchmarkOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_benchmarks(session, filters, page, q=q)


@router.post(
    "/benchmarks",
    status_code=201,
    response_model=BenchmarkOut,
    responses=responses_for(409, 422, 429),
)
async def create_benchmark(
    request: Request, body: BenchmarkCreate, principal: StaffDep, session: Session
) -> BenchmarkOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.create_benchmark(session, body, principal.user_id)


@router.patch(
    "/benchmarks/{benchmark_id}",
    response_model=BenchmarkOut,
    responses=responses_for(404, 409, 422, 429),
)
async def update_benchmark(
    request: Request,
    benchmark_id: UUID,
    body: BenchmarkPatch,
    principal: StaffDep,
    session: Session,
) -> BenchmarkOut:
    await enforce_user_limit(request, "wods-write", principal.user_id)
    return await service.update_benchmark(session, benchmark_id, body, principal.user_id)
