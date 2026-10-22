"""Router de settings (US-054; blueprint del Sprint 2, B1; S2-D3 y S2-D15).

Plano, con la ruta completa en cada decorador y `require_role("admin")` en las ocho rutas.
Las tipadas (`gym`, `privacy`, `memberships`) se declaran ANTES que la genérica
`/settings/{section}` para ganar el emparejamiento; `section` es `str` (no enum) para que una
clave desconocida dé 404 `section_not_available` y no 422.

El coach recibe 403 en las ocho (S2-D14): lee el nombre del gimnasio por `GET /auth/me`.
Las rutas no hacen `select`: validan el cuerpo, llaman al service y devuelven.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.security import Principal, require_role
from app.modules.settings import service
from app.modules.settings.schemas import (
    GymPatchIn,
    GymSectionOut,
    MembershipsPatchIn,
    MembershipsSectionOut,
    PrivacyPatchIn,
    PrivacySectionOut,
    SectionKey,
    SectionOut,
    SectionPatchIn,
)

router = APIRouter(  # M6 y M7
    tags=["settings"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)
_PATCH = responses_for(409)  # `VersionConflict`
_GENERICA = responses_for(404)  # `SectionNotAvailable`

Admin = Annotated[Principal, Depends(require_role("admin"))]
Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api


@router.get("/settings/gym", response_model=GymSectionOut)
async def get_gym(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.gym)


@router.patch("/settings/gym", response_model=GymSectionOut, responses=_PATCH)
async def patch_gym(body: GymPatchIn, principal: Admin, session: Session) -> SectionOut:
    return await service.update_section(
        session, SectionKey.gym, body.value.model_dump(mode="json"), body.version, principal.user_id
    )


@router.get("/settings/privacy", response_model=PrivacySectionOut)
async def get_privacy(principal: Admin, session: Session) -> SectionOut:
    return await service.get_section(session, SectionKey.privacy)


@router.patch("/settings/privacy", response_model=PrivacySectionOut, responses=_PATCH)
async def patch_privacy(body: PrivacyPatchIn, principal: Admin, session: Session) -> SectionOut:
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
    body: MembershipsPatchIn, principal: Admin, session: Session
) -> SectionOut:
    return await service.update_section(
        session,
        SectionKey.memberships,
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
    section: str, body: SectionPatchIn, principal: Admin, session: Session
) -> SectionOut:
    return await service.update_section(
        session, section, body.value, body.version, principal.user_id
    )
