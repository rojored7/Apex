"""Router de auth (S2-B2: US-042, US-043, US-044). Plano, con la ruta completa en cada
decorador (S2-D3).

- `POST /auth/login` (público): `rate_limit("login")`, `require_same_origin`, `no_store`; pone
  la cookie del refresh y devuelve `LoginOut` sin el refresh.
- `POST /auth/refresh` (público, por la cookie): `rate_limit("refresh")`, `require_same_origin`,
  `no_store`; un `InvalidRefresh` sale con el `Set-Cookie` que borra la cookie. El cuerpo se
  ignora.
- `POST /auth/logout` (público, por la cookie; H-1): `rate_limit("logout")`,
  `require_same_origin`; siempre 204 y siempre borra la cookie.
Las rutas no hacen `select`: leen la cookie, llaman al service y devuelven. `Settings` sale de
`request.app.state.settings` (cookie `Secure`, orígenes y política).
"""

from __future__ import annotations

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.ratelimit import client_ip, rate_limit
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
from app.modules.auth.schemas import LoginIn, LoginOut, RefreshOut

router = APIRouter(tags=["auth"])

Session = Annotated[AsyncSession, Depends(get_session)]


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


__all__ = ["router", "service"]
