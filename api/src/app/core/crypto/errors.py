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
    "signature_invalid",
    "plaintext",
    "id_immutable",
    "index_manual",
    "crypto_key_changed",
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


UnavailableReason = Literal["sealed", "unreachable", "forbidden", "not_loaded"]


class CryptoUnavailable(CryptoError):
    """El custodio de llaves no responde o está sellado (S5-D14, S5-D17); `code` fijo
    `crypto_unavailable` y `reason` distingue la causa. Nunca lleva URL, token ni cuerpo."""

    def __init__(self, reason: UnavailableReason, message: str | None = None) -> None:
        super().__init__(
            "crypto_unavailable", message or f"custodio de llaves no disponible: {reason}"
        )
        self.reason: UnavailableReason = reason

    def __repr__(self) -> str:
        return f"CryptoUnavailable({self.reason!r})"
