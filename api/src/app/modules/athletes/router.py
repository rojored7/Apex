"""Router de `athletes` (S9-A1, US-178; contrato del blueprint §3, rutas 1 y 2).

Plano, con la ruta completa en el decorador (S2-D3). Admin y coach (`StaffDep`).
- `POST /athletes/{member_id}/metrics`: 201 `MetricOut`; `athletes-write`.
- `GET /athletes/{member_id}/metrics`: `Page[MetricOut]`; `staff-read`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams
from app.core.ratelimit import enforce_user_limit
from app.core.security import StaffDep
from app.modules.athletes import service
from app.modules.athletes.schemas import MetricIn, MetricOut

router = APIRouter(
    tags=["athletes"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep


@router.post(
    "/athletes/{member_id}/metrics",
    status_code=201,
    response_model=MetricOut,
    responses=responses_for(404, 409, 422, 429),
)
async def add_metric(
    request: Request, member_id: UUID, body: MetricIn, principal: StaffDep, session: Session
) -> MetricOut:
    await enforce_user_limit(request, "athletes-write", principal.user_id)
    return await service.add_metric(session, member_id, body, by=principal.user_id)


@router.get(
    "/athletes/{member_id}/metrics",
    response_model=Page[MetricOut],
    responses=responses_for(404, 422, 429),
)
async def list_metrics(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    include_voided: bool = False,
) -> Page[MetricOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_metrics(session, member_id, page, include_voided=include_voided)
