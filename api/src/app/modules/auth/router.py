"""Router de auth (S2-B2: US-042, US-043, US-044). Plano, con la ruta completa en cada
decorador (S2-D3).

- `POST /auth/login` (público): `rate_limit("login")`, `require_same_origin`, `no_store`; pone
  la cookie del refresh y devuelve `LoginOut` sin el refresh.
- `POST /auth/refresh` (público, por la cookie): `rate_limit("refresh")`, `require_same_origin`,
  `no_store`; un `InvalidRefresh` sale con el `Set-Cookie` que borra la cookie. El cuerpo se
  ignora.
- `POST /auth/logout` (público, por la cookie; H-1): `rate_limit("logout")`,
  `require_same_origin`; siempre 204 y siempre borra la cookie.
- `GET /auth/me` y `POST /auth/me/password` (S2-B3; los tres roles con
  `allow_pending_password=True`, `no_store`): el segundo responde 200 `AccessTokenOut` con un
  access nuevo (S2-D37) y lee la cookie `apex_refresh` para dejar viva esa sesión.
- `GET /users` (admin, `PageParams`, `q`, `role`, `status`; `no_store`) y `POST /users`
  (admin, 201 `CreateUserOut` con `activation_url`; `no_store`).
Las rutas no hacen `select`: leen la cookie, llaman al service y devuelven. `Settings` sale de
`request.app.state.settings` (cookie `Secure`, orígenes y política).
"""

from __future__ import annotations

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import client_ip, rate_limit
from app.core.security import Principal, require_role
from app.modules.auth import service
from app.modules.auth.cookies import (
    clear_cookie_header,
    clear_refresh_cookie,
    no_store,
    policy_from,
    read_refresh_cookie,
    require_same_origin,
    set_refresh_cookie,
)
from app.modules.auth.exceptions import InvalidRefresh
from app.modules.auth.schemas import (
    AccessTokenOut,
    ChangePasswordIn,
    CreateUserIn,
    CreateUserOut,
    LoginIn,
    LoginOut,
    MeOut,
    RefreshOut,
    Role,
    UserRow,
    UserStatus,
)

router = APIRouter(tags=["auth"])
# Revisión de seguridad S2-B3: cada intento cuesta hasta tres argon2; tope por IP.
CHANGE_PASSWORD_IP_LIMIT: Final = 10

Session = Annotated[AsyncSession, Depends(get_session)]
# M-8: solo "Mi cuenta" admite una cuenta que debe cambiar la contraseña.
Pending = Annotated[
    Principal, Depends(require_role("admin", "coach", "member", allow_pending_password=True))
]
Admin = Annotated[Principal, Depends(require_role("admin"))]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _ip(request: Request) -> str:
    redes: Sequence[IPv4Network | IPv6Network] = getattr(request.app.state, "trusted_proxies", ())
    return client_ip(request, redes)


@router.post(
    "/auth/login",
    response_model=LoginOut,
    dependencies=[
        Depends(rate_limit("login")),
        Depends(require_same_origin),
        Depends(no_store),
    ],
)
async def login(body: LoginIn, request: Request, response: Response, session: Session) -> LoginOut:
    settings = _settings(request)
    resultado = await service.login(
        session,
        body.email,
        body.password.get_secret_value(),
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        policy=policy_from(settings),
    )
    set_refresh_cookie(response, resultado.refresh_token, settings)
    return LoginOut(
        access_token=resultado.access_token,
        expires_in=resultado.expires_in,
        user=resultado.user,
        must_change_password=resultado.must_change_password,
    )


@router.post(
    "/auth/refresh",
    response_model=RefreshOut,
    dependencies=[
        Depends(rate_limit("refresh")),
        Depends(require_same_origin),
        Depends(no_store),
    ],
)
async def refresh(request: Request, response: Response, session: Session) -> RefreshOut:
    settings = _settings(request)
    try:
        resultado = await service.refresh(
            session,
            read_refresh_cookie(request),
            user_agent=request.headers.get("user-agent"),
            policy=policy_from(settings),
        )
    except InvalidRefresh as error:
        if error.clear_cookie:
            error.headers["Set-Cookie"] = clear_cookie_header(settings)
        raise
    set_refresh_cookie(response, resultado.refresh_token, settings)
    return RefreshOut(access_token=resultado.access_token, expires_in=resultado.expires_in)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(rate_limit("logout")), Depends(require_same_origin)],
)
async def logout(request: Request, session: Session) -> Response:
    await service.logout(session, read_refresh_cookie(request))
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(respuesta, _settings(request))
    return respuesta


@router.get("/auth/me", response_model=MeOut, dependencies=[Depends(no_store)])
async def me(principal: Pending, session: Session) -> MeOut:
    return await service.me(session, principal)


@router.post(
    "/auth/me/password",
    response_model=AccessTokenOut,
    dependencies=[
        Depends(rate_limit("change-password", CHANGE_PASSWORD_IP_LIMIT)),
        Depends(no_store),
    ],
)
async def change_password(
    body: ChangePasswordIn, request: Request, principal: Pending, session: Session
) -> AccessTokenOut:
    return await service.change_password(
        session,
        principal.user_id,
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
        current_refresh=read_refresh_cookie(request),
        policy=policy_from(_settings(request)),
    )


@router.get("/users", response_model=Page[UserRow], dependencies=[Depends(no_store)])
async def list_users(
    principal: Admin,
    session: Session,
    page: Annotated[PageParams, Depends()],
    q: SearchQuery = None,
    role: Role | None = None,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
) -> Page[UserRow]:
    return await service.list_users(session, q=q, role=role, status=user_status, page=page)


@router.post(
    "/users",
    response_model=CreateUserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(no_store)],
)
async def create_user(
    body: CreateUserIn, request: Request, principal: Admin, session: Session
) -> CreateUserOut:
    return await service.create_user(
        session,
        email=body.email,
        role=body.role,
        by=principal.user_id,
        front_base_url=_settings(request).FRONT_BASE_URL,
    )


__all__ = ["router", "service"]
