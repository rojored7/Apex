"""Router de `results` (S8-B1, S8-B3; US-169). Plano, con la ruta completa en el decorador (S2-D3).

- `PUT /results`: registra (o corrige, con `supersedes_id`) el resultado de un socio en un WOD;
  admin y coach (`StaffDep`; el socio recibe 403); `results-write` (60 por minuto por usuario).
  201 `ResultOut`. Códigos 201, 401, 403, 404, 409, 422 y 429. El origen (`source`) es `desk`, o
  `kiosk` con la marca del quiosco (S8-D31).
- `GET /class-sessions/{session_id}/attendance`: los asistentes vivos con su resultado vigente en
  el WOD efectivo; `staff-read`, paginada. En quiosco, solo clases de hoy o de ayer (S8-D15).
- `GET /wods/{wod_id}/leaderboard?level&sex` (S8-B4, US-171), `GET /wods/{wod_id}/results?
  include_superseded` (US-172) y `GET /members/{member_id}/results?benchmark` (US-173): lecturas de
  `staff-read`, paginadas con `PageParams` y `no-store`; 404 si el WOD o el socio no existen.
La ruta no hace `select`: valida, llama al service y devuelve.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep, StaffDep
from app.modules.results import service
from app.modules.results.schemas import (
    LeaderboardRow,
    MemberResultRow,
    ResultIn,
    ResultLevel,
    ResultOut,
    SessionAttendanceOut,
    VoidIn,
    WodResultRow,
)

router = APIRouter(
    tags=["results"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep


@router.put(
    "/results",
    status_code=201,
    response_model=ResultOut,
    responses=responses_for(404, 409, 422, 429),
)
async def put_result(
    request: Request, body: ResultIn, principal: StaffDep, session: Session
) -> ResultOut:
    await enforce_user_limit(request, "results-write", principal.user_id)
    return await service.record_result(
        session, body, by=principal.user_id, source="kiosk" if principal.kiosk else "desk"
    )


@router.get(
    "/class-sessions/{session_id}/attendance",
    response_model=SessionAttendanceOut,
    responses=responses_for(404, 422, 429),
)
async def session_attendance(
    request: Request,
    session_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
) -> SessionAttendanceOut:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.session_attendance(session, session_id, page, kiosk=principal.kiosk)


@router.get(
    "/wods/{wod_id}/leaderboard",
    response_model=Page[LeaderboardRow],
    responses=responses_for(404, 422, 429),
)
async def get_leaderboard(
    request: Request,
    wod_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    level: ResultLevel | None = None,
    sex: Literal["f", "m"] | None = None,
) -> Page[LeaderboardRow]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.leaderboard(session, wod_id, page, level=level, sex=sex)


@router.get(
    "/wods/{wod_id}/results",
    response_model=Page[WodResultRow],
    responses=responses_for(404, 422, 429),
)
async def list_wod_results(
    request: Request,
    wod_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    include_superseded: bool = False,
) -> Page[WodResultRow]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_wod_results(
        session, wod_id, page, include_superseded=include_superseded
    )


@router.get(
    "/members/{member_id}/results",
    response_model=Page[MemberResultRow],
    responses=responses_for(404, 422, 429),
)
async def list_member_results(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    benchmark: bool | None = None,
) -> Page[MemberResultRow]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_member_results(session, member_id, page, benchmark=benchmark)


@router.post(
    "/results/{result_id}/void",
    response_model=ResultOut,
    responses=responses_for(404, 409, 422, 429),
)
async def void_result(
    request: Request, result_id: UUID, body: VoidIn, principal: AdminDep, session: Session
) -> ResultOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.void_result(session, result_id, body, by=principal.user_id)
