"""Router de socios (S2-B7, US-069; L-1). Plano, con la ruta completa en el decorador (S2-D3).

- `POST /members` (admin y coach): 201 `MemberDetailOut` enmascarado. Límite por usuario
  autenticado (`enforce_user_limit(request, "members-write", user_id)`, L-1; por defecto 60 altas
  por minuto, `USER_MEMBERS_WRITE_LIMIT_PER_MIN`); el alta 61 da 429. Códigos 201, 401, 403,
  409, 422 y 429.
- `GET /members` (admin y coach; S2-B8, US-070): `Page[MemberRowOut]` con `PageParams`, `q`
  (`SearchQuery`, hasta 100; nunca se registra), `status` y `sort`. Solo cuando hay `q`, límite
  por usuario de búsquedas (`PII_SEARCH_BUCKET`, por defecto 60 por minuto,
  `USER_SEARCH_LIMIT_PER_MIN`; L-1); sin `q` no cuenta. S3-B9b (US-071, D22): `membership_status`
  y `plan_id` (422 con `field`; un plan inexistente da la lista vacía). S7-R2 (US-163, S7-D15):
  `last_attendance` (`7d|14d|30d|60d|never`, 422 con `field`; consume `staff-read` solo con el
  filtro) y las columnas `last_attendance_at` y `membership_classes_remaining`. Códigos 200, 401,
  403, 422 y 429.
- `GET /members/{member_id}` (admin y coach, también sobre un dado de baja, N-20; S3-B9b,
  US-073): `MemberDetailOut` con los cinco campos enmascarados (D20). Límite por usuario
  `members-detail` (M-2, S3-D45; por defecto 120 por minuto, `USER_DETAIL_LIMIT_PER_MIN`).
  Códigos 200, 401, 403, 404, 422 y 429.
S3-B10 (US-074, US-075, US-076; D19, D21, M-1, M-3, S3-D44, S3-D46):
- `POST /members/{member_id}/reveal` (admin y coach): `RevealOut` en claro de un campo cifrado.
  Tres ventanas por usuario: `members-reveal` (30 por minuto), `members-reveal-hour` (200 por
  hora) y `members-reveal-day` (600 por día). La IP de `client_ip` va a la auditoría (L-12).
  Códigos 200, 401, 403, 404, 422 y 429. Al pasar de la mitad del cupo horario (la 101 de 200)
  registra `logger.warning("reveal volume", extra={"user_id", "count"})` (S3-D44, M-1).
- `PATCH /members/{member_id}` (admin y coach): `MemberDetailOut` enmascarado; consume
  `members-write` (compartido con `POST /members`). Códigos 200, 401, 403, 404, 409, 422 y 429.
- `DELETE /members/{member_id}` (solo admin): 204. Códigos 204, 401, 403, 404, 409, 422 y 429.
- `POST /members/{member_id}/reactivate` (solo admin): `MemberDetailOut`. Códigos 200, 401, 403,
  404, 409, 422 y 429.
- Las dos consumen `admin-write` (30 por minuto, `USER_ADMIN_WRITE_LIMIT_PER_MIN`; L1 de la
  revisión de Fase 4 del Sprint 3), la cubeta de anular un pago y anular una membresía.
S4A-B5 (US-106; S4A-D20, S4A-D45):
- `GET /members/{member_id}/audit` (admin y coach, también sobre un dado de baja):
  `Page[MemberHistoryItem]` con `PageParams` y `q`; consume `staff-read` (120 por minuto,
  compartida con `GET /audit`, `GET /audit/{seq}` y el tablero). Códigos 200, 401, 403, 404, 422
  (`offset` mayor que 100.000 con `field="offset"`) y 429.
El 429 se declara por ruta, nunca en el `APIRouter` (D27, E2). Las rutas no hacen `select`:
validan, llaman al service y devuelven.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Final, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.export import ExportStream, begin_export
from app.core.http import csv_download, no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import (
    PII_SEARCH_BUCKET,
    USER_LIMITS,
    client_ip,
    enforce_user_limit,
    usage,
)
from app.core.security import AdminDep, StaffDep
from app.modules.attachments.schemas import AttachmentOut
from app.modules.audit.schemas import MemberHistoryItem
from app.modules.members import service
from app.modules.members.exceptions import MemberValidationError
from app.modules.members.schemas import (
    DEFAULT_MEMBER_SORT,
    ChannelsOut,
    ChannelsPatch,
    LastAttendanceFilter,
    MemberCreate,
    MemberDetailOut,
    MemberExportQuery,
    MemberListQuery,
    MemberPatch,
    MemberRowOut,
    MembershipFilterStatus,
    MemberSort,
    MemberStatusFilter,
    RevealIn,
    RevealOut,
)

# M6: datos de personas (nombres y máscaras): ninguna respuesta se guarda en caché.
router = APIRouter(
    tags=["members"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api

logger = logging.getLogger("app.members")

REVEAL_HOUR_BUCKET = "members-reveal-hour"  # la ventana del aviso `reveal volume` (S3-D44)


@router.post(
    "/members",
    status_code=201,
    response_model=MemberDetailOut,
    responses=responses_for(409, 429),
)
async def create_member(
    request: Request, body: MemberCreate, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-write", principal.user_id)
    return await service.create(session, body)


KIOSK_MIN_QUERY: Final = 3
"""Letras mínimas de la búsqueda en quiosco (S7-C4c, M-2): con una letra se recorre el padrón."""
KIOSK_MAX_LIMIT: Final = 20
"""Filas máximas por página en quiosco: `limit` se acota, no se rechaza (S7-C4c, M-2)."""


def _check_kiosk_list(q: str | None, sort: str, **filtros: object) -> None:
    """Revisión de C4 (M-3) y de R2/C4b (M-2): con la marca de quiosco `GET /members` exige `q` de
    al menos `KIOSK_MIN_QUERY` letras (sin contar espacios), no admite orden distinto del de
    siempre y rechaza los filtros de estado, plan, consentimiento y última asistencia (422 con
    `field`)."""
    for campo, valor in filtros.items():
        if valor is not None:
            raise MemberValidationError(
                message="En modo quiosco solo se busca por nombre.", field=campo
            )
    if sort != DEFAULT_MEMBER_SORT:
        raise MemberValidationError(message="En modo quiosco no se ordena.", field="sort")
    if q is None or len(q.strip()) < KIOSK_MIN_QUERY:
        raise MemberValidationError(
            message=f"En modo quiosco escribe al menos {KIOSK_MIN_QUERY} letras.", field="q"
        )


@router.get("/members", response_model=Page[MemberRowOut], responses=responses_for(429))
async def list_members(
    request: Request,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    member_status: Annotated[MemberStatusFilter | None, Query(alias="status")] = None,
    sort: MemberSort = DEFAULT_MEMBER_SORT,
    membership_status: MembershipFilterStatus | None = None,
    plan_id: UUID | None = None,
    consent: Literal["missing"] | None = None,
    last_attendance: LastAttendanceFilter | None = None,
) -> Page[MemberRowOut]:
    if principal.kiosk:  # el quiosco solo busca por nombre; nada de recorrer la situación (M-3)
        _check_kiosk_list(
            q,
            sort,
            status=member_status,
            membership_status=membership_status,
            plan_id=plan_id,
            consent=consent,
            last_attendance=last_attendance,
        )
        page = PageParams(limit=min(page.limit, KIOSK_MAX_LIMIT), offset=page.offset)
    if q:
        await enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)
    if last_attendance:  # S7-R2 (US-163, S7-D15): consulta a `classes`, cubeta de lecturas caras
        await enforce_user_limit(request, "staff-read", principal.user_id)
    filtros = MemberListQuery(
        q=q,
        status=member_status,
        sort=sort,
        membership_status=membership_status,
        plan_id=plan_id,
        consent=consent,
        last_attendance=last_attendance,
    )
    return await service.list(session, filtros, page)


@router.get(
    "/members/export",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/csv": {"schema": {"type": "string"}}}},
        **responses_for(409, 422, 429),
    },
)
async def export_members(
    request: Request,
    principal: AdminDep,
    session: Session,
    q: SearchQuery = None,
    member_status: Annotated[MemberStatusFilter | None, Query(alias="status")] = None,
    membership_status: MembershipFilterStatus | None = None,
    plan_id: UUID | None = None,
    consent: Literal["missing"] | None = None,
    last_attendance: LastAttendanceFilter | None = None,
) -> StreamingResponse:
    """US-138 (S5-D41, S5-D60): CSV de socios en streaming, solo admin; va antes de `/{id}`."""

    async def preparar() -> ExportStream:
        # El flujo único va antes que las cubetas: un 409 no gasta cupo (S5-D82).
        await enforce_user_limit(request, "export", principal.user_id)
        await enforce_user_limit(request, "export-hour", principal.user_id)
        await enforce_user_limit(request, "export-day", principal.user_id)
        filtros = MemberExportQuery(
            q=q,
            status=member_status,
            membership_status=membership_status,
            plan_id=plan_id,
            consent=consent,
            last_attendance=last_attendance,
        )
        return await service.export_members(
            session,
            filtros,
            by=principal.user_id,
            ip=_ip(request),
            max_rows=request.app.state.settings.EXPORT_MAX_ROWS,
        )

    flujo, cuerpo = await begin_export(principal.user_id, preparar)
    return csv_download(cuerpo, flujo.filename)


@router.get(
    "/members/{member_id}",
    response_model=MemberDetailOut,
    responses=responses_for(404, 422, 429),
)
async def get_member(
    request: Request, member_id: UUID, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-detail", principal.user_id)
    return await service.get(session, member_id)


@router.get(
    "/members/{member_id}/audit",
    response_model=Page[MemberHistoryItem],
    responses=responses_for(404, 422, 429),
)
async def member_history(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
) -> Page[MemberHistoryItem]:
    # Literal: `test_user_limits_catalog.py` exige la cubeta como constante (S4A-D45).
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.history(session, member_id, page, q)


@router.post(
    "/members/{member_id}/attachments",
    status_code=201,
    response_model=AttachmentOut,
    responses=responses_for(404, 408, 409, 413, 422, 429),
)
async def attach_to_member(
    request: Request,
    member_id: UUID,
    kind: Literal["photo", "consent", "other"],
    principal: StaffDep,
    session: Session,
) -> AttachmentOut:
    """S6-C2 (US-148, S6-D59): cuerpo crudo. Orden: socio, rol por `kind`, 409 (S6-C3),
    `Content-Length`, cubeta y recién entonces se lee el cuerpo."""
    await service.ensure_exists(session, member_id)
    service.ensure_can_upload(principal.role, kind)
    # S6-C3: la política se consulta antes de soltar la conexión y antes de leer el cuerpo.
    await service.ensure_consent_upload(session, member_id, kind)
    # S6-D114 (revisión de seguridad de C2): el socio ya se validó; se suelta la conexión para
    # no retenerla «idle in transaction» mientras el cliente manda el cuerpo (hasta 30 s, D84).
    # `store` vuelve a abrir la transacción al escribir y `get_session` confirma al salir.
    await session.rollback()
    service.ensure_declared_size(request.headers.get("content-length"))
    await enforce_user_limit(request, "attachments-upload", principal.user_id)
    return await service.attach(
        session, member_id, kind=kind, chunks=request.stream(), by=principal.user_id
    )


@router.get(
    "/members/{member_id}/attachments",
    response_model=Page[AttachmentOut],
    responses=responses_for(404, 422, 429),
)
async def list_member_attachments(
    request: Request,
    member_id: UUID,
    principal: StaffDep,
    session: Session,
    page: Annotated[PageParams, Depends()],
) -> Page[AttachmentOut]:
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.list_attachments(session, member_id, page)


def _ip(request: Request) -> str:
    redes: Sequence[IPv4Network | IPv6Network] = getattr(request.app.state, "trusted_proxies", ())
    return client_ip(request, redes)


async def _avisar_volumen_de_reveal(request: Request, user_id: UUID) -> None:
    """S3-D44 (M-1): `reveal volume` cuando el usuario pasa de la mitad de su cupo horario. El
    conteo incluye la petición actual (con un tope de 200, la 101 avisa y la 100 no); el registro
    lleva el usuario y el conteo, nunca el socio ni el valor."""
    topes: Mapping[str, tuple[int, int]] = getattr(request.app.state, "user_limits", USER_LIMITS)
    tope, ventana = topes[REVEAL_HOUR_BUCKET]
    conteo = await usage(REVEAL_HOUR_BUCKET, str(user_id), window_s=ventana)
    if conteo * 2 > tope:
        logger.warning("reveal volume", extra={"user_id": str(user_id), "count": conteo})


@router.post(
    "/members/{member_id}/reveal",
    response_model=RevealOut,
    responses=responses_for(404, 422, 429),
)
async def reveal_member_field(
    request: Request, member_id: UUID, body: RevealIn, principal: StaffDep, session: Session
) -> RevealOut:
    # Literales: `test_user_limits_catalog.py` exige el bucket como constante en la llamada.
    await enforce_user_limit(request, "members-reveal", principal.user_id)
    await enforce_user_limit(request, "members-reveal-hour", principal.user_id)
    await enforce_user_limit(request, "members-reveal-day", principal.user_id)
    await _avisar_volumen_de_reveal(request, principal.user_id)
    return await service.reveal(session, member_id, body.field, ip=_ip(request))


@router.patch(
    "/members/{member_id}",
    response_model=MemberDetailOut,
    responses=responses_for(403, 404, 409, 422, 429),
)
async def update_member(
    request: Request, member_id: UUID, body: MemberPatch, principal: StaffDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "members-write", principal.user_id)
    return await service.update(session, member_id, body, role=principal.role)


@router.delete(
    "/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(404, 409, 422, 429),
)
async def deactivate_member(
    request: Request, member_id: UUID, principal: AdminDep, session: Session
) -> None:
    # Sin `Response` propia: FastAPI arma el 204 con las cabeceras de `no_store`.
    await enforce_user_limit(request, "admin-write", principal.user_id)
    await service.deactivate(session, member_id)


@router.post(
    "/members/{member_id}/reactivate",
    response_model=MemberDetailOut,
    responses=responses_for(404, 409, 422, 429),
)
async def reactivate_member(
    request: Request, member_id: UUID, principal: AdminDep, session: Session
) -> MemberDetailOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.reactivate(session, member_id)


@router.get(
    "/members/{member_id}/channels",
    response_model=ChannelsOut,
    responses=responses_for(404, 422, 429),
)
async def get_member_channels(
    request: Request, member_id: UUID, principal: StaffDep, session: Session
) -> ChannelsOut:
    """S5-B5 (US-123): también sobre un dado de baja (N-20); consume `staff-read`."""
    await enforce_user_limit(request, "staff-read", principal.user_id)
    return await service.get_channels(session, member_id)


@router.patch(
    "/members/{member_id}/channels",
    response_model=ChannelsOut,
    responses=responses_for(404, 409, 422, 429),
)
async def set_member_channels(
    request: Request, member_id: UUID, body: ChannelsPatch, principal: StaffDep, session: Session
) -> ChannelsOut:
    await enforce_user_limit(request, "notifications-write", principal.user_id)
    return await service.set_channels(session, member_id, body.items, principal.user_id)
