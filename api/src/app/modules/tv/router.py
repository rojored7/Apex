"""Router de la TV (S8-C2; US-176, S8-D18, S8-D33). Plano (S2-D3).

`GET /tv/today` sin rol: la protege la dependencia `device_token` (marca `__apex_device_token__`),
que lee SOLO `X-Device-Token` (un `?token=`, `Authorization` y las cookies no cuentan). Valida
PRIMERO el token; si es válido aplica solo la cubeta `tv` por hash del token (`KeyKind account`);
si no, comprueba y suma `tv-fail` por IP y responde 401 `unauthorized` uniforme.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.db import SessionDep
from app.core.errors import UnauthorizedError, responses_for
from app.core.http import no_store
from app.core.ratelimit import DEFAULT_WINDOW_S, client_ip, enforce, ip_bucket_key
from app.core.security import hash_opaque_token
from app.modules.settings.schemas import TvConfig
from app.modules.tv import service
from app.modules.tv.schemas import TvBoard

DEVICE_TOKEN_HEADER = "x-device-token"  # noqa: S105 - nombre de cabecera, no un secreto
TOKEN_KEY_CHARS = 16

router = APIRouter(tags=["tv"], dependencies=[Depends(no_store)])


def _topes(request: Request) -> Mapping[str, tuple[int, int]]:
    return getattr(request.app.state, "rate_limits", {})


async def device_token(request: Request, session: SessionDep) -> TvConfig:
    token = request.headers.get(DEVICE_TOKEN_HEADER)
    config = await service.authenticate(session, token)
    topes = _topes(request)
    if config is None or token is None:
        redes: Sequence[IPv4Network | IPv6Network] = getattr(
            request.app.state, "trusted_proxies", ()
        )
        limite, ventana = topes.get("tv-fail", (12, DEFAULT_WINDOW_S))
        clave = ip_bucket_key(client_ip(request, redes), ipv4_prefix=32)
        await enforce("tv-fail", clave, limit=limite, window_s=ventana, kind="ip")
        raise UnauthorizedError()
    limite, ventana = topes.get("tv", (30, DEFAULT_WINDOW_S))
    clave = hash_opaque_token(token)[:TOKEN_KEY_CHARS]
    await enforce("tv", clave, limit=limite, window_s=ventana, kind="account")
    return config


device_token.__apex_device_token__ = True  # type: ignore[attr-defined]


@router.get("/tv/today", response_model=TvBoard, responses=responses_for(401, 429))
async def tv_today(
    config: Annotated[TvConfig, Depends(device_token)], session: SessionDep
) -> TvBoard:
    return await service.today(session, config)
