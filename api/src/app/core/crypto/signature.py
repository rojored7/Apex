"""Formato de la firma `apx1.<key_id>.<alg>.<sig_b64url>` (US-027 T2; N-04; ADR-002).

Cuatro partes, sin nonce. `alg` en `SIGNATURE_ALGS` (`Ed25519` en v0.1; `ML-DSA-65` con
EP-17/EP-26 sin cambiar a quien firma). Funciones puras; los errores no incluyen la firma.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.crypto.errors import CryptoError

ED25519_PUBLIC_LEN: Final = 32
SIGNATURE_PREFIX: Final = "apx1"
SIGNATURE_ALGS: Final[frozenset[str]] = frozenset({"Ed25519", "ML-DSA-65"})
_PARTS: Final = 4
_ALFABETO: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@dataclass(frozen=True)
class SignatureParts:
    key_id: UUID
    alg: str
    sig: bytes


def format_signature(key_id: UUID, alg: str, sig: bytes) -> str:
    if alg not in SIGNATURE_ALGS:
        raise CryptoError("unsupported", f"algoritmo de firma no soportado: {alg}")
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return ".".join([SIGNATURE_PREFIX, str(key_id).lower(), alg, sig_b64])


def parse_signature(signature: str) -> SignatureParts:
    partes = signature.split(".")
    if len(partes) != _PARTS:
        raise CryptoError("signature_invalid", "la firma debe tener exactamente cuatro partes")
    prefijo, key_texto, alg, sig_texto = partes
    if prefijo != SIGNATURE_PREFIX:
        raise CryptoError("signature_invalid", "la firma no tiene el prefijo apx1")
    try:
        key_id = UUID(key_texto)
    except ValueError:
        raise CryptoError("signature_invalid", "el key_id de la firma no es un UUID") from None
    if alg not in SIGNATURE_ALGS:
        raise CryptoError("signature_invalid", "la firma usa un algoritmo no soportado")
    if not sig_texto or any(c not in _ALFABETO for c in sig_texto):
        raise CryptoError("signature_invalid", "la firma no es base64url válido")
    try:
        sig = base64.urlsafe_b64decode(sig_texto + "=" * (-len(sig_texto) % 4))
    except (binascii.Error, ValueError):
        raise CryptoError("signature_invalid", "la firma no es base64url válido") from None
    return SignatureParts(key_id, alg, sig)


def verify_ed25519(public_key: str, data: bytes, signature: bytes) -> bool:
    """Verifica Ed25519 en proceso con la clave pública (base64 estándar de 32 bytes; S6-D62).

    `False` ante una firma que no corresponde, de largo incorrecto o una clave malformada; nunca
    devuelve `True` por una excepción tragada. No llama a ningún proveedor.
    """
    try:
        crudo = base64.b64decode(public_key, validate=True)
        if len(crudo) != ED25519_PUBLIC_LEN:
            return False
        Ed25519PublicKey.from_public_bytes(crudo).verify(signature, data)
    except (InvalidSignature, binascii.Error, ValueError, TypeError):
        return False
    return True
