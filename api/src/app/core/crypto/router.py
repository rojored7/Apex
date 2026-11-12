"""Router de llaves (EP-18; S6-D12, S6-D44, S6-D52, S6-B1).

`GET /crypto/keys`, `/crypto/ops` y `/crypto/jobs` (admin, `staff-read`; S6-B2, US-144).
`main.py` lo registra bajo `/api/v1` y cablea la puerta de auditoría con
`set_audit_writer`; el router nunca importa `core.audit` ni `app.modules`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.clock import current_clock
from app.core.crypto import inventory
from app.core.crypto.cbom import CBOM_FORMAT, build_cbom
from app.core.crypto.models import DATA_CLASS_PATTERN
from app.core.crypto.schemas import (
    CryptoJobOut,
    CryptoOpOut,
    JobKind,
    JobsFilters,
    KeysFilters,
    KeysPage,
    OpsFilters,
    OpVerb,
)
from app.core.db import DatabaseBusy, SessionDep
from app.core.errors import responses_for
from app.core.http import file_download, no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import enforce_user_limit
from app.core.security import AdminDep

AuditWriter = Callable[..., Awaitable[Any]]

router = APIRouter(
    tags=["crypto"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

_audit_writer: AuditWriter | None = None


def set_audit_writer(fn: AuditWriter | None) -> None:
    """Puerta de auditoría que cablea `main.py` (S6-D52); `None` la quita (pruebas)."""
    global _audit_writer
    _audit_writer = fn


def audit_writer_registered() -> bool:
    return _audit_writer is not None


@router.get("/crypto/keys", response_model=KeysPage, responses=responses_for(422, 429))
async def list_crypto_keys(
    request: Request,
    principal: AdminDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    purpose: Literal["encrypt", "index", "sign"] | None = None,
    state: Literal["active", "decrypt_only", "retired"] | None = None,
    provider: Literal["local", "openbao"] | None = None,
    data_class: Annotated[str | None, Query(pattern=DATA_CLASS_PATTERN, max_length=100)] = None,
) -> KeysPage:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filtros = KeysFilters(
        purpose=purpose, state=state, provider=provider, data_class=data_class, q=q
    )
    pagina = await inventory.list_keys(session, filtros, page)
    return KeysPage(
        items=pagina.items,
        total=pagina.total,
        limit=pagina.limit,
        offset=pagina.offset,
        summary=await inventory.summary(session),
    )


@router.get("/crypto/ops", response_model=Page[CryptoOpOut], responses=responses_for(422, 429))
async def list_crypto_ops(
    request: Request,
    principal: AdminDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    verb: OpVerb | None = None,
    data_class: Annotated[str | None, Query(pattern=DATA_CLASS_PATTERN, max_length=100)] = None,
    key_id: UUID | None = None,
    user_id: UUID | None = None,
    result: Literal["ok", "error"] | None = None,
    batch_id: UUID | None = None,
) -> Page[CryptoOpOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filtros = OpsFilters(
        start=from_,
        end=to,
        verb=verb,
        data_class=data_class,
        key_id=key_id,
        user_id=user_id,
        result=result,
        batch_id=batch_id,
        q=q,
    )
    return await inventory.list_ops(session, filtros, page)


@router.get("/crypto/jobs", response_model=Page[CryptoJobOut], responses=responses_for(422, 429))
async def list_crypto_jobs(
    request: Request,
    principal: AdminDep,
    session: SessionDep,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    status: Literal["pending", "running", "done", "failed"] | None = None,
    kind: JobKind | None = None,
    data_class: Annotated[str | None, Query(pattern=DATA_CLASS_PATTERN, max_length=100)] = None,
) -> Page[CryptoJobOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    filtros = JobsFilters(status=status, kind=kind, data_class=data_class, q=q)
    return await inventory.list_jobs(session, filtros, page)


@router.get(
    "/crypto/cbom",
    responses=responses_for(429)
    | {200: {"content": {"application/json": {}}, "description": "CBOM apex-cbom/1"}},
)
async def export_cbom(request: Request, principal: AdminDep, session: SessionDep) -> Response:
    """CBOM `apex-cbom/1` como descarga JSON (S6-B3, US-146). Audita `export` por la puerta
    registrada (S6-D52) en la misma transacción y ANTES del cuerpo; sin puerta, 503 `busy`."""
    await enforce_user_limit(request, "cbom-export", principal.user_id)
    escritor = _audit_writer
    if escritor is None:
        raise DatabaseBusy()
    settings = request.app.state.settings
    reloj = current_clock()
    llaves = await inventory.all_keys(session)
    resumen = await inventory.summary(session)
    cbom = build_cbom(
        llaves,
        app_version=settings.APP_VERSION,
        generated_at=reloj.now_utc(),
        provider=resumen.provider,
        tls_declared=bool(settings.APEX_DOMAIN),
    )
    await escritor(
        session,
        action="export",
        table_name="crypto.crypto_keys",
        record_id=None,
        before=None,
        after={"count": len(llaves), "format": CBOM_FORMAT},
        user_id=principal.user_id,
    )
    cuerpo = json.dumps(cbom, ensure_ascii=False, indent=2).encode("utf-8")
    return file_download(
        cuerpo,
        filename=f"apex-cbom-{reloj.today_bogota().isoformat()}.json",
        media_type="application/json; charset=utf-8",
    )
