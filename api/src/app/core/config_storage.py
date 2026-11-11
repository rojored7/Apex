"""Reglas puras de almacenamiento S3 y dominio público de `Settings` (S6-W0-5; S6-D21, D65, D77).

Funciones sin dependencias de `Settings`: devuelven los nombres (jamás valores) de las variables
inválidas o ausentes, y `Settings` los convierte en `ConfigError`. Se separan de `config.py` para
que éste no pase de 800 líneas.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlsplit

# Las cinco variables de S3 son todo o nada cuando `STORAGE_PROVIDER=s3` (S6-D21).
S3_REQUIRED: Final[tuple[str, ...]] = (
    "S3_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_REGION",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
)

# Etiquetas DNS: letras, dígitos y guion (sin `_`), sin guion al inicio ni al final.
_ETIQUETA = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST = re.compile(rf"{_ETIQUETA}(?:[.]{_ETIQUETA})*")
_PUERTO = re.compile(r"[0-9]{1,5}")


def s3_problems(
    *,
    provider: str,
    env: str,
    allow_production: bool,
    values: dict[str, object | None],
) -> tuple[list[str], list[str]]:
    """`(faltan, inválidas)` de la configuración de S3; con almacén local no se valida nada."""
    if provider != "s3":
        return [], []
    faltan = [nombre for nombre in S3_REQUIRED if values.get(nombre) is None]
    invalidas: list[str] = []
    endpoint = values.get("S3_ENDPOINT_URL")
    if isinstance(endpoint, str) and not _endpoint_ok(endpoint, env):
        invalidas.append("S3_ENDPOINT_URL")
    if env == "production" and not allow_production:
        invalidas.append("S3_ENABLE_PRODUCTION")
    return faltan, invalidas


def _endpoint_ok(endpoint: str, env: str) -> bool:
    """Solo esquema y host (con puerto y ruta opcionales): sin credenciales, consulta ni fragmento.

    Unas credenciales dentro de la URL saltarían la redacción de `SecretStr` (revisión de
    seguridad de S6-W0-5).
    """
    url = urlsplit(endpoint)
    if not url.hostname:
        return False
    if url.username is not None or url.password is not None or url.query or url.fragment:
        return False
    return url.scheme == "https" or (url.scheme == "http" and env == "dev")


def domain_problems(domain: str | None, allow_port: bool) -> list[str]:
    """Nombres de las variables inválidas de `APEX_DOMAIN` y `ALLOW_DOMAIN_PORT` (S6-D77 final).

    `APEX_DOMAIN` es `host[:puerto]`. Con puerto solo pasa si `ALLOW_DOMAIN_PORT=true` y el host es
    `*.localhost`; la bandera con un host que no es `*.localhost` falla con cualquier `ENV`.
    """
    if domain is None:
        return []
    host, separador, puerto = domain.partition(":")
    if _HOST.fullmatch(host) is None:
        return ["APEX_DOMAIN"]
    if separador and (_PUERTO.fullmatch(puerto) is None or not 0 < int(puerto) <= 65535):
        return ["APEX_DOMAIN"]
    es_localhost = host.lower().endswith(".localhost")
    if separador and not (allow_port and es_localhost):
        return ["APEX_DOMAIN", "ALLOW_DOMAIN_PORT"]
    if allow_port and not es_localhost:
        return ["ALLOW_DOMAIN_PORT"]
    return []
