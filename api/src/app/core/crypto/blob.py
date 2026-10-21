"""Formato del blob cifrado (US-025 T2; CLAUDE.md bus 4; ADR-002, irreversible).

`apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`: cinco partes, base64url sin
relleno, `key_id` UUID en minúsculas, `alg` en `SUPPORTED_ALGS` (`A256GCM` en v0.1; el
algoritmo va en el dato, no en el código), nonce de 12 bytes. Funciones puras, sin
primitivas. Los errores nunca incluyen el blob.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.core.crypto.errors import CryptoError

BLOB_PREFIX: Final = "apx1"
SUPPORTED_ALGS: Final[frozenset[str]] = frozenset({"A256GCM"})
NONCE_LEN: Final = 12
PARTS: Final = 5


@dataclass(frozen=True)
class BlobParts:
    version: str
    key_id: UUID
    alg: str
    nonce: bytes
    ciphertext: bytes


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(texto: str) -> bytes:
    if not texto or any(c not in _B64URL_ALFABETO for c in texto):
        raise CryptoError("blob_invalid", "el blob no es base64url válido")
    relleno = "=" * (-len(texto) % 4)
    try:
        return base64.urlsafe_b64decode(texto + relleno)
    except (binascii.Error, ValueError):
        raise CryptoError("blob_invalid", "el blob no es base64url válido") from None


_B64URL_ALFABETO: Final = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


def format_blob(key_id: UUID, alg: str, nonce: bytes, ciphertext: bytes) -> str:
    if alg not in SUPPORTED_ALGS:
        raise CryptoError("unsupported", f"algoritmo no soportado: {alg}")
    if len(nonce) != NONCE_LEN:
        raise CryptoError("blob_invalid", "el nonce debe medir 12 bytes")
    return ".".join([BLOB_PREFIX, str(key_id).lower(), alg, _b64url(nonce), _b64url(ciphertext)])


def parse_blob(blob: str) -> BlobParts:
    partes = blob.split(".")
    if len(partes) != PARTS:
        raise CryptoError("blob_invalid", "el blob debe tener exactamente cinco partes")
    version, key_texto, alg, nonce_texto, ct_texto = partes
    if version != BLOB_PREFIX:
        raise CryptoError("blob_invalid", "el blob no tiene el prefijo apx1")
    try:
        key_id = UUID(key_texto)
    except ValueError:
        raise CryptoError("blob_invalid", "el key_id del blob no es un UUID") from None
    if alg not in SUPPORTED_ALGS:
        raise CryptoError("blob_invalid", "el blob usa un algoritmo no soportado")
    nonce = _unb64url(nonce_texto)
    if len(nonce) != NONCE_LEN:
        raise CryptoError("blob_invalid", "el nonce del blob no mide 12 bytes")
    return BlobParts(version, key_id, alg, nonce, _unb64url(ct_texto))
