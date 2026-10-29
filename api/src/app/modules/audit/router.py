"""Router del módulo `audit` (S4A-B3, US-104; S4A-D14, S4A-D47). Plano, con la ruta completa en el
decorador (S2-D3).

- `GET /audit/verify/last` (admin, `AdminDep`): 200 `VerifyResultOut | null` (nunca 404). Sin
  límite por usuario (lee una fila, M-1) y sin parámetros (sin 422). Se registra antes de
  `GET /audit/{seq}` (S4A-B4).
- `POST /audit/verify` (admin, `AdminDep`): consume `audit-verify` (3 por minuto) y
  `audit-verify-hour` (20 por hora) por usuario (M-3, S4A-D47). 200 `VerifyResultOut` (hasta
  `SYNC_VERIFY_MAX_ROWS` filas), 202 `VerifyStartedOut` (segundo plano; la respuesta lleva
  `Cache-Control: no-store` a mano porque es un `JSONResponse`), 409 `verification_running`,
  429. Sin cuerpo: sin 422.
- `GET /audit` (admin; S4A-B4, US-102; S4A-D16, S4A-D45, S4A-D46): `Page[AuditRow]` con
  `PageParams`, `q` y los filtros `from` (alias), `to`, `user_id`, `table` (patrón y longitud),
  `record_id`, `subject_member_id` y `action`; consume `staff-read`; 422 y 429. S4A-D106:
  `record_id` exige `table`, `table` debe ser auditada y `total` se satura en 100.001 (lo dice
  `AUDIT_LIST_DESCRIPTION` en el contrato).
- `GET /audit/{seq}` (admin; S4A-B4, US-103; S4A-D17, S4A-D46): `seq` entre 1 y `MAX_SEQ`
  (422 fuera de rango, nunca 500), `AuditDetail`, consume `staff-read`; 404
  `audit_entry_not_found`, 422 y 429. Se registra DESPUÉS de `GET /audit/verify/last`.
Las rutas no hacen `select`: aplican el límite, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.core.audit import AuditAction
from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import NO_STORE, no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep
from app.modules.audit import service
from app.modules.audit.schemas import (
    MAX_AUDIT_OFFSET,
    MAX_SEQ,
    TABLE_MAX_LENGTH,
    TABLE_PATTERN,
    AuditDetail,
    AuditListQuery,
    AuditRow,
    VerifyResultOut,
    VerifyStartedOut,
)

AUDIT_LIST_DESCRIPTION: Final = (
    "Auditoría en `seq` descendente (solo admin). `total` se satura en "
    f"{MAX_AUDIT_OFFSET + 1} (S4A-D106). `record_id` exige `table`; un `q` UUID filtra "
    "`record_id` solo con `table`; `table` debe ser una tabla auditada."
)

router = APIRouter(
    tags=["audit"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get("/audit/verify/last", response_model=VerifyResultOut | None)
async def last_verification(principal: AdminDep, session: SessionDep) -> VerifyResultOut | None:
    vista = await service.last_verification(session)
    return None if vista is None else VerifyResultOut.model_validate(vista, from_attributes=True)


@router.post(
    "/audit/verify",
    response_model=VerifyResultOut,
    responses={
        **responses_for(409, 429),
        202: {"model": VerifyStartedOut, "description": "La verificación sigue en segundo plano."},
    },
)
async def verify_chain(
    request: Request, principal: AdminDep, session: SessionDep
) -> VerifyResultOut | JSONResponse:
    await enforce_user_limit(request, "audit-verify", principal.user_id)
    await enforce_user_limit(request, "audit-verify-hour", principal.user_id)
    salida = await service.verify(session, by=principal.user_id)
    if isinstance(salida, service.Started):
        last = (
            None
            if salida.last is None
            else VerifyResultOut.model_validate(salida.last, from_attributes=True)
        )
        cuerpo = VerifyStartedOut(last=last).model_dump(mode="json")
        return JSONResponse(status_code=202, content=cuerpo, headers={"Cache-Control": NO_STORE})
    return VerifyResultOut.model_validate(salida.result, from_attributes=True)


@router.get(
    "/audit",
    response_model=Page[AuditRow],
    responses=responses_for(422, 429),
    description=AUDIT_LIST_DESCRIPTION,
)
async def list_audit(
    request: Request,
    principal: AdminDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: AwareDatetime | None = None,
    user_id: UUID | None = None,
    table: Annotated[str | None, Query(pattern=TABLE_PATTERN, max_length=TABLE_MAX_LENGTH)] = None,
    record_id: UUID | None = None,
    subject_member_id: UUID | None = None,
    action: AuditAction | None = None,
) -> Page[AuditRow]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filtros = AuditListQuery(
        q=q,
        from_=from_,
        to=to,
        user_id=user_id,
        table=table,
        record_id=record_id,
        subject_member_id=subject_member_id,
        action=action,
    )
    return await service.list_entries(session, filtros, page)


@router.get("/audit/{seq}", response_model=AuditDetail, responses=responses_for(404, 422, 429))
async def audit_entry(
    request: Request,
    seq: Annotated[int, Path(ge=1, le=MAX_SEQ)],
    principal: AdminDep,
    session: SessionDep,
) -> AuditDetail:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.get_entry(session, seq)
