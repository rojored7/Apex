"""HMAC-SHA-256 para el índice ciego (US-026 T2). Único sitio con `hmac` fuera de pruebas."""

from __future__ import annotations

import hashlib
import hmac


def hmac_sha256_hex(key: bytes | bytearray, data: bytes) -> str:
    return hmac.new(bytes(key), data, hashlib.sha256).hexdigest()
