"""Errores del bus de criptografía (US-023 T1). Nunca llevan material de llave."""

from __future__ import annotations

from typing import Literal

CryptoCode = Literal[
    "kek_missing",
    "kek_insecure_permissions",
    "kek_invalid",
    "unwrap_failed",
    "unknown_provider",
    "unsupported",
    "key_missing",
    "key_retired",
    "unknown_data_class",
    "no_index",
    "empty_value",
    "blob_invalid",
    "decrypt_failed",
    "crypto_unavailable",
]


class CryptoError(Exception):
    """Error del bus con un `code` fijo y un mensaje sin bytes ni rutas secretas."""

    def __init__(self, code: CryptoCode, message: str) -> None:
        super().__init__(message)
        self.code: CryptoCode = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"CryptoError({self.code!r})"
