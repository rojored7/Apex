"""Piezas puras del protocolo de OpenBao Transit (S5-B1): errores, versión y respuestas.

Sin httpx y sin leer el token; lo importa solo `openbao_provider.py`. Ninguna excepción copia el
cuerpo ni la URL del servidor (S5-D17).
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import urlsplit

from app.core.config import OPENBAO_HTTP_HOSTS
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.provider import KeyInfo

_VERSION: Final = re.compile(rb"^vault:v(\d+):")
_KEY_REF: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def map_error(status: int, errors: Sequence[str]) -> CryptoError:
    """Pura; nunca copia el cuerpo (S5-D17). `unwrap_failed` solo para un 400 (S5-D162)."""
    texto = " ".join(errors).lower()
    if status == 503 and ("sealed" in texto or "not initialized" in texto):
        return CryptoUnavailable("sealed")
    if status in (401, 403):
        return CryptoUnavailable("forbidden")
    if status == 404:
        return CryptoError("key_missing", "el custodio de llaves no tiene esa llave")
    if status == 400:
        return CryptoError("unwrap_failed", "el custodio de llaves rechazó la operación")
    return CryptoUnavailable("unreachable")  # 429, 5xx y todo lo demás: reintentable


def parse_version(wrapped: bytes) -> int:
    """`n` de `vault:v<n>:...`; `CryptoError("unwrap_failed")` si no tiene el prefijo."""
    coincide = _VERSION.match(wrapped)
    if coincide is None:
        raise CryptoError("unwrap_failed", "la envoltura no tiene el prefijo vault:v<n>:")
    return int(coincide.group(1))


def comprobar_direccion(addr: str) -> str:
    partes = urlsplit(addr)
    https = partes.scheme == "https" and bool(partes.hostname)
    http_interno = partes.scheme == "http" and partes.hostname in OPENBAO_HTTP_HOSTS
    if not (https or http_interno):
        raise CryptoError("unknown_provider", "dirección de OpenBao no permitida (https o interna)")
    return addr.rstrip("/")


def b64(datos: bytes | bytearray) -> str:
    return base64.b64encode(datos).decode("ascii")


def ruta(accion: str, key_ref: str) -> str:
    if not _KEY_REF.match(key_ref):
        raise CryptoError("key_missing", "referencia de llave no válida")
    return f"/v1/transit/{accion}/{key_ref}"


def a_texto(datos: bytes) -> str:
    try:
        return datos.decode("ascii")
    except UnicodeDecodeError:
        raise CryptoError("unwrap_failed", "la envoltura no es texto") from None


def texto_cifrado(datos: dict[str, Any]) -> bytes:
    texto = datos.get("ciphertext")
    if not isinstance(texto, str):
        raise CryptoError("unwrap_failed", "respuesta inválida del custodio")
    resultado = texto.encode("ascii", errors="replace")
    parse_version(resultado)
    return resultado


def info(key_ref: str, datos: dict[str, Any]) -> KeyInfo:
    try:
        version = int(datos["latest_version"])
        creada = datos["keys"][str(version)]
        if isinstance(creada, dict):  # llaves asimétricas: {"creation_time": "..."}
            instante = datetime.fromisoformat(str(creada["creation_time"]))
        else:
            instante = datetime.fromtimestamp(int(creada), UTC)
        return KeyInfo(
            key_ref=key_ref,
            algorithm=str(datos["type"]),
            provider="openbao",
            version=version,
            created_at=instante,
        )
    except (KeyError, TypeError, ValueError):
        raise CryptoError("unwrap_failed", "respuesta inválida del custodio") from None
