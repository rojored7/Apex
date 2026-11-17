"""Router de `athletes` (S9-A1, US-178; contrato del blueprint §3, rutas 1 y 2).

Plano, con la ruta completa en el decorador (S2-D3). Admin y coach (`StaffDep`).
- `POST /athletes/{member_id}/metrics`: 201 `MetricOut`; `athletes-write`.
- `GET /athletes/{member_id}/metrics`: `Page[MetricOut]`; `staff-read`.
- `POST /athletes/{member_id}/metrics/{metric_id}/reveal` (S9-A2, US-179): `MetricRevealOut`;
  las tres cubetas `members-reveal*` de la ficha y `warn_reveal_volume` (S9-D15, S9-D35).
- `POST` y `GET /athletes/{member_id}/records` (S9-B1, US-180; rutas 4 y 5): `RecordOut`.
- `POST /athletes/{member_id}/metrics/{metric_id}/void` (S9-A3, S9-D13): `MetricOut`;
  `athletes-write`. Sin cuerpo; el coach solo anula lo suyo y dentro de 24 h (S9-D33).
"""

from __future__ import annotations

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams
from app.core.ratelimit import client_ip, enforce_user_limit, warn_reveal_volume
from app.core.security import StaffDep
from app.modules.athletes import service
from app.modules.athletes.schemas import (
    MetricIn,
    MetricOut,
    MetricRevealIn,
    MetricRevealOut,
    RecordIn,
    RecordKind,
    RecordOut,
)

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


@router.post(
    "/athletes/{member_id}/metrics/{metric_id}/reveal",
    response_model=MetricRevealOut,
    responses=responses_for(404, 409, 422, 429),
)
async def reveal_metric(
    request: Request,
    member_id: UUID,
    metric_id: UUID,
    body: MetricRevealIn,
    principal: StaffDep,
    session: Session,
) -> MetricRevealOut:
    # Literales: `test_user_limits_catalog.py` exige las cubetas como constantes en la llamada.
    # Son las tres de la ficha del socio (S9-D15): un cupo propio duplicaría lo que se ve en claro.
    await enforce_user_limit(request, "members-reveal", principal.user_id)
    await enforce_user_limit(request, "members-reveal-hour", principal.user_id)
    await enforce_user_limit(request, "members-reveal-day", principal.user_id)
    await warn_reveal_volume(request, principal.user_id)
    redes: Sequence[IPv4Network | IPv6Network] = getattr(request.app.state, "trusted_proxies", ())
    return await service.reveal_metric(
        session,
        member_id,
        metric_id,
        body.field,
        ip=client_ip(request, redes),
        role=principal.role,
    )


@router.post(
    "/athletes/{member_id}/metrics/{metric_id}/void",
    response_model=MetricOut,
    responses=responses_for(404, 409, 422, 429),
)
async def void_metric(
    request: Request, member_id: UUID, metric_id: UUID, principal: StaffDep, session: Session
) -> MetricOut:
    await enforce_user_limit(request, "athletes-write", principal.user_id)
    return await service.void_metric(
        session, member_id, metric_id, by=principal.user_id, role=principal.role
    )


@router.post(
    "/athletes/{member_id}/records",
    status_code=201,
    response_model=RecordOut,
    responses=responses_for(404, 409, 422, 429),
)
async def add_record(
    request: Request, member_id: UUID, body: RecordIn, principal: StaffDep, session: Session
) -> RecordOut:
    await enforce_user_limit(request, "athletes-write", principal.user_id)
    return await service.add_record(session, member_id, body, by=principal.user_id)


@router.get(
    "/athletes/{member_id}/records",
    response_model=Page[RecordOut],
    responses=responses_for(404, 422, 429),
)
async def list_records(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    kind: RecordKind | None = None,
    include_invalidated: bool = False,
) -> Page[RecordOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_records(
        session, member_id, page, kind=kind, include_invalidated=include_invalidated
    )
