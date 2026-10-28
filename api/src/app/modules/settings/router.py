"""Router de settings (US-054; blueprint del Sprint 2, B1; S2-D3 y S2-D15).

Plano, con la ruta completa en cada decorador y `require_role("admin")` en las diez rutas.
Las tipadas (`gym`, `privacy`, `memberships` y, desde S3-B3, `payment_methods`) se declaran ANTES
que la genérica `/settings/{section}` para ganar el emparejamiento; `section` es `str` (no enum)
para que una clave desconocida dé 404 `section_not_available` y no 422.

El coach recibe 403 en las diez (S2-D14): lee el nombre del gimnasio por `GET /auth/me`.
Los cinco `PATCH` consumen `admin-write` (30 por minuto por usuario, la cubeta de las demás
escrituras de solo admin; M-A de V10, S3-D100) y declaran 429; los `GET` no tienen tope.
Las rutas no hacen `select`: validan el cuerpo, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import Principal, require_role
from app.modules.settings import service
from app.modules.settings.schemas import (
    GymPatchIn,
    GymSectionOut,
    MembershipsPatchIn,
    MembershipsSectionOut,
    PaymentMethodsPatchIn,
    PaymentMethodsSectionOut,
    PrivacyPatchIn,
    PrivacySectionOut,
    SectionKey,
    SectionOut,
    SectionPatchIn,
)

router = APIRouter(  # M6 y M7
    tags=["settings"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)
_PATCH = responses_for(409, 429)  # `VersionConflict` y el tope `admin-write`
_GENERICA = responses_for(404)  # `SectionNotAvailable`

Admin = Annotated[Principal, Depends(require_role("admin"))]
Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.get("/settings/gym", response_model=GymSectionOut)
async def get_gym(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.gym)


@router.patch("/settings/gym", response_model=GymSectionOut, responses=_PATCH)
async def patch_gym(
    request: Request, body: GymPatchIn, principal: Admin, session: Session
) -> SectionOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update_section(
        session, SectionKey.gym, body.value.model_dump(mode="json"), body.version, principal.user_id
    )


@router.get("/settings/privacy", response_model=PrivacySectionOut)
async def get_privacy(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.privacy)


@router.patch("/settings/privacy", response_model=PrivacySectionOut, responses=_PATCH)
async def patch_privacy(
    request: Request, body: PrivacyPatchIn, principal: Admin, session: Session
) -> SectionOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update_section(
        session,
        SectionKey.privacy,
        body.value.model_dump(mode="json"),
        body.version,
        principal.user_id,
    )


@router.get("/settings/memberships", response_model=MembershipsSectionOut)
async def get_memberships(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.memberships)


@router.patch("/settings/memberships", response_model=MembershipsSectionOut, responses=_PATCH)
async def patch_memberships(
    request: Request, body: MembershipsPatchIn, principal: Admin, session: Session
) -> SectionOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update_section(
        session,
        SectionKey.memberships,
        body.value.model_dump(mode="json"),
        body.version,
        principal.user_id,
    )


@router.get("/settings/payment_methods", response_model=PaymentMethodsSectionOut)
async def get_payment_methods(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.payment_methods)


@router.patch(
    "/settings/payment_methods", response_model=PaymentMethodsSectionOut, responses=_PATCH
)
async def patch_payment_methods(
    request: Request, body: PaymentMethodsPatchIn, principal: Admin, session: Session
) -> SectionOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update_section(
        session,
        SectionKey.payment_methods,
        body.value.model_dump(mode="json"),
        body.version,
        principal.user_id,
    )


# Genéricas: después de las tipadas (el orden de declaración importa).


@router.get("/settings/{section}", response_model=SectionOut, responses=_GENERICA)
async def get_section(section: str, principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, section)


@router.patch("/settings/{section}", response_model=SectionOut, responses={**_GENERICA, **_PATCH})
async def patch_section(
    request: Request, section: str, body: SectionPatchIn, principal: Admin, session: Session
) -> SectionOut:
    await enforce_user_limit(request, "admin-write", principal.user_id)
    return await service.update_section(
        session, section, body.value, body.version, principal.user_id
    )
