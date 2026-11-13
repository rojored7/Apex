"""Origen público, CORS y cookie coherentes con `APEX_DOMAIN` (S6-E1, US-153; D28, D65, D77).

`core/config.py` los reexporta (como `config_storage`) para que `app.core.config` siga siendo la
puerta. Con `APEX_DOMAIN` el origen público es `https://<dominio>`; sin él, `FRONT_BASE_URL`
(modo LAN, S4B-D154). Los mensajes nombran variables, nunca valores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings


def public_origin(settings: Settings) -> str:
    """`https://<APEX_DOMAIN>` (con puerto si lo lleva) o, sin dominio, `FRONT_BASE_URL`."""
    if settings.APEX_DOMAIN:
        return f"https://{settings.APEX_DOMAIN.lower()}"  # el navegador envía el host en minúsculas
    return settings.FRONT_BASE_URL.rstrip("/")


def _problemas_con_dominio(settings: Settings, origen: str) -> list[str]:
    invalidas: list[str] = []
    if any(o.lower().startswith("http:") for o in settings.CORS_ORIGINS):
        invalidas.append("CORS_ORIGINS")
    if settings.FRONT_BASE_URL.rstrip("/").lower() != origen:
        invalidas.append("FRONT_BASE_URL")
    sesion = settings.AUTH_ALLOWED_ORIGINS
    if any(o.lower().startswith("http:") for o in sesion) or (sesion and origen not in sesion):
        invalidas.append("AUTH_ALLOWED_ORIGINS")
    if not settings.COOKIE_SECURE:
        invalidas.append("COOKIE_SECURE")
    if settings.ALLOW_INSECURE_COOKIE:
        invalidas.append("ALLOW_INSECURE_COOKIE")
    return invalidas


def validate_origins(settings: Settings) -> None:
    """Con dominio: `CORS_ORIGINS` sin `http:`, `FRONT_BASE_URL` igual a `public_origin`,
    `COOKIE_SECURE=true` y `ALLOW_INSECURE_COOKIE=false`; sin dominio rige S4B-D154 (en
    producción `COOKIE_SECURE` salvo la excepción P7). Falla con `ConfigError` nombrando la
    variable."""
    from app.core.config import ConfigError  # perezoso: config importa este módulo

    if settings.APEX_DOMAIN:
        invalidas = _problemas_con_dominio(settings, public_origin(settings))
    elif settings.ENV == "production" and not (
        settings.COOKIE_SECURE or settings.ALLOW_INSECURE_COOKIE
    ):
        invalidas = ["COOKIE_SECURE"]
    else:
        invalidas = []
    if invalidas:
        raise ConfigError(missing=[], invalid=invalidas)


def cookie_secure(settings: Settings) -> bool:
    """El atributo `Secure` de la cookie del refresh: `COOKIE_SECURE`."""
    return settings.COOKIE_SECURE
