"""Cookie del refresh y dependencias HTTP de las rutas de sesión (S2-B2; L-8, M-1, L-1;
S2-D4, privado del módulo auth).

- `apex_refresh`: `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age` de
  `REFRESH_TOKEN_TTL_DAYS` y `Secure` según `COOKIE_SECURE`; se borra con los mismos atributos
  (`Max-Age=0`).
- `no_store` se movió a `core/http.py` (revisión Python M6): lo usan todas las rutas con rol.
- `require_same_origin`: `Origin` (o `Referer`) contra `AUTH_ALLOWED_ORIGINS` o el origen de
  `FRONT_BASE_URL`; sin ninguno de los dos acepta `Sec-Fetch-Site: same-origin|none`; si no,
  403 `forbidden` sin tocar la cookie (S2-D38).
- `policy_from(settings)`: la `AuthPolicy` de `Settings`.
Los valores de `Settings` salen de `request.app.state.settings`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.modules.auth.rules import AuthPolicy

REFRESH_COOKIE: Final = "apex_refresh"
REFRESH_COOKIE_PATH: Final = "/api/v1/auth"
SECONDS_PER_DAY: Final = 86400
SAME_ORIGIN_FETCH_SITES: Final = frozenset({"same-origin", "none"})


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * SECONDS_PER_DAY,
        path=REFRESH_COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_cookie_header(settings: Settings) -> str:
    """El valor de `Set-Cookie` que borra la cookie, para adjuntarlo a una excepción."""
    respuesta = Response()
    clear_refresh_cookie(respuesta, settings)
    return respuesta.headers["set-cookie"]


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE) or None


def policy_from(settings: Settings) -> AuthPolicy:
    return AuthPolicy(
        access_ttl_s=settings.ACCESS_TOKEN_TTL_S,
        refresh_ttl=timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        refresh_absolute_ttl=timedelta(days=settings.REFRESH_ABSOLUTE_TTL_DAYS),
        reuse_grace=timedelta(seconds=settings.REFRESH_REUSE_GRACE_S),
        account_limit=settings.LOGIN_ACCOUNT_LIMIT,
        account_window_s=settings.LOGIN_ACCOUNT_WINDOW_S,
        account_global_limit=settings.LOGIN_ACCOUNT_GLOBAL_LIMIT,
        account_global_window_s=settings.LOGIN_ACCOUNT_GLOBAL_WINDOW_S,
        lock_after=settings.LOGIN_LOCK_AFTER,
        min_duration_ms=settings.LOGIN_MIN_DURATION_MS,
    )


def _origin_of(url: str) -> str | None:
    partes = urlsplit(url)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        return None
    return f"{partes.scheme}://{partes.netloc}"


def allowed_origins(settings: Settings) -> frozenset[str]:
    """`AUTH_ALLOWED_ORIGINS` o, si está vacía, el origen de `FRONT_BASE_URL`."""
    if settings.AUTH_ALLOWED_ORIGINS:
        return frozenset(settings.AUTH_ALLOWED_ORIGINS)
    propio = _origin_of(settings.FRONT_BASE_URL)
    return frozenset({propio}) if propio else frozenset()


def is_same_origin(
    origin: str | None, referer: str | None, fetch_site: str | None, allowed: frozenset[str]
) -> bool:
    """Pura (M-1): manda `Origin`; sin él, `Referer`; sin ninguno, `Sec-Fetch-Site`."""
    if origin is not None:
        return origin in allowed
    if referer is not None:
        return _origin_of(referer) in allowed
    return fetch_site is not None and fetch_site.lower() in SAME_ORIGIN_FETCH_SITES


async def require_same_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    cabeceras = request.headers
    if not is_same_origin(
        cabeceras.get("origin"),
        cabeceras.get("referer"),
        cabeceras.get("sec-fetch-site"),
        allowed_origins(settings),
    ):
        raise ForbiddenError("forbidden")
