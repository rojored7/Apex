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
- S2-B4: `POST /auth/forgot` (público, `rate_limit("forgot")`, siempre 204 sin cuerpo; H-2),
  `POST /auth/reset` (público, `rate_limit("reset")`, 204; L-12) y
  `POST /users/{user_id}/resend-link` (admin, `no_store`, 200 `IssuedLinkOut`). Forgot y reset no
  usan la cookie: no llevan `require_same_origin` (S2-D38 la exige solo a login, refresh y
  logout).
- S2-B5: `GET`, `PATCH` y `DELETE /users/{user_id}` (204) y `POST /users/{user_id}/lock`,
  `/unlock` (200 `UserOut`) y `/revoke-sessions` (200 `RevokeSessionsOut`); todas solo admin
  con `no_store`.
Las rutas no hacen `select`: leen la cookie, llaman al service y devuelven. `Settings` sale de
`request.app.state.settings` (cookie `Secure`, orígenes y política).
"""

from __future__ import annotations

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.config import Settings
from app.core.db import SessionDep
from app.core.errors import responses_for
from app.core.http import no_store
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.ratelimit import client_ip, rate_limit
from app.core.security import Principal, require_role
from app.modules.auth import rules, service
from app.modules.auth.cookies import (
    clear_cookie_header,
    clear_refresh_cookie,
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
    ForgotIn,
    IssuedLinkOut,
    LoginIn,
    LoginOut,
    MeOut,
    RefreshOut,
    ResetIn,
    RevokeSessionsOut,
    Role,
    UpdateUserIn,
    UserOut,
    UserRow,
    UserStatus,
)

router = APIRouter(tags=["auth"])
# Revisión de seguridad S2-B3: cada intento cuesta hasta tres argon2; tope por IP.
CHANGE_PASSWORD_IP_LIMIT: Final = 10

Session = SessionDep  # N-1: commit antes de responder; un solo alias en todo el api
# M-8: solo "Mi cuenta" admite una cuenta que debe cambiar la contraseña.
Pending = Annotated[
    Principal, Depends(require_role("admin", "coach", "member", allow_pending_password=True))
]
Admin = Annotated[Principal, Depends(require_role("admin"))]

# M7 (revisión general): cada ruta publica solo los errores que puede devolver.
_ADMIN = responses_for(401, 403)  # sin sesión; rol ajeno o `password_change_required`
_ADMIN_SOBRE_CUENTA = responses_for(401, 403, 404)  # y `user_not_found`


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _ip(request: Request) -> str:
    redes: Sequence[IPv4Network | IPv6Network] = getattr(request.app.state, "trusted_proxies", ())
    return client_ip(request, redes)


@router.post(
    "/auth/login",
    response_model=LoginOut,
    responses=responses_for(401, 403, 429),
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
    responses=responses_for(401, 403, 429),
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
    responses=responses_for(403, 429),
    dependencies=[Depends(rate_limit("logout")), Depends(require_same_origin)],
)
async def logout(request: Request, session: Session) -> Response:
    await service.logout(session, read_refresh_cookie(request))
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(respuesta, _settings(request))
    return respuesta


@router.get(
    "/auth/me", response_model=MeOut, responses=responses_for(401), dependencies=[Depends(no_store)]
)
async def me(principal: Pending, session: Session) -> MeOut:
    return await service.me(session, principal)


@router.post(
    "/auth/me/password",
    response_model=AccessTokenOut,
    responses=responses_for(401, 429),
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


@router.get(
    "/users", response_model=Page[UserRow], responses=_ADMIN, dependencies=[Depends(no_store)]
)
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
    responses=responses_for(401, 403, 409),
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


@router.post(
    "/auth/forgot",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(429),
    dependencies=[Depends(rate_limit("forgot"))],
)
async def forgot(body: ForgotIn, request: Request) -> Response:
    await service.forgot(body.email, policy=policy_from(_settings(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(400, 429),
    dependencies=[Depends(rate_limit("reset"))],
)
async def reset(body: ResetIn, session: Session) -> Response:
    await service.reset(session, body.token, body.new_password.get_secret_value())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/resend-link",
    response_model=IssuedLinkOut,
    responses=responses_for(401, 403, 404, 409),
    dependencies=[Depends(no_store)],
)
async def resend_link(
    user_id: UUID, request: Request, principal: Admin, session: Session
) -> IssuedLinkOut:
    return await service.resend_link(
        session,
        user_id,
        by=principal.user_id,
        front_base_url=_settings(request).FRONT_BASE_URL,
    )


# S2-B5 · ciclo de vida del usuario (US-049, US-050, US-051) -------------------------------


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    responses=_ADMIN_SOBRE_CUENTA,
    dependencies=[Depends(no_store)],
)
async def get_user(user_id: UUID, principal: Admin, session: Session) -> UserOut:
    return rules.user_out(await service.get_user(session, user_id))


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    responses=responses_for(401, 403, 404, 409),
    dependencies=[Depends(no_store)],
)
async def update_user(
    user_id: UUID, body: UpdateUserIn, principal: Admin, session: Session
) -> UserOut:
    usuario = await service.update_user(
        session, user_id, email=body.email, role=body.role, by=principal.user_id
    )
    return rules.user_out(usuario)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=responses_for(401, 403, 404, 409),
    dependencies=[Depends(no_store)],
)
async def delete_user(user_id: UUID, principal: Admin, session: Session) -> None:
    # Sin `Response` propia: FastAPI arma el 204 con las cabeceras de `no_store`.
    await service.delete_user(session, user_id, by=principal.user_id)


@router.post(
    "/users/{user_id}/lock",
    response_model=UserOut,
    responses=responses_for(401, 403, 404, 409),
    dependencies=[Depends(no_store)],
)
async def lock_user(user_id: UUID, principal: Admin, session: Session) -> UserOut:
    return rules.user_out(await service.lock(session, user_id, by=principal.user_id))


@router.post(
    "/users/{user_id}/unlock",
    response_model=UserOut,
    responses=responses_for(401, 403, 404, 409),
    dependencies=[Depends(no_store)],
)
async def unlock_user(user_id: UUID, principal: Admin, session: Session) -> UserOut:
    return rules.user_out(await service.unlock(session, user_id, by=principal.user_id))


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=RevokeSessionsOut,
    responses=_ADMIN_SOBRE_CUENTA,
    dependencies=[Depends(no_store)],
)
async def revoke_sessions(user_id: UUID, principal: Admin, session: Session) -> RevokeSessionsOut:
    revocadas = await service.revoke_sessions(session, user_id, by=principal.user_id)
    return RevokeSessionsOut(revoked=revocadas)


__all__ = ["router", "service"]
