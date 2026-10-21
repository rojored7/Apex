"""AES-256-GCM (US-025 T3). Junto con `local_provider.py`, el único sitio con `AESGCM`.

`open_` convierte `InvalidTag` en `CryptoError("decrypt_failed")` con un mensaje único:
no distingue AAD equivocado de ciphertext alterado (sin oráculo).
"""

from __future__ import annotations

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.crypto.errors import CryptoError

DECRYPT_FAILED_MESSAGE = "el dato cifrado no se puede abrir"


def seal(dek: bytes | bytearray, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    return AESGCM(bytes(dek)).encrypt(nonce, plaintext, aad)


def open_(dek: bytes | bytearray, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(bytes(dek)).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise CryptoError("decrypt_failed", DECRYPT_FAILED_MESSAGE) from None
