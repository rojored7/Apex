"""Router de llaves (EP-18; S6-D12, S6-D44, S6-D52, S6-B1).

`GET /crypto/keys` (admin, `staff-read`). `main.py` lo registra bajo `/api/v1` y cablea la puerta
de auditoría con `set_audit_writer`; el router nunca importa `core.audit` ni `app.modules`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.core.crypto import inventory
from app.core.crypto.models import DATA_CLASS_PATTERN
from app.core.crypto.schemas import KeysFilters, KeysPage
from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import PageParams, SearchQuery
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
