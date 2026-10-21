"""La única puerta del bus de criptografía (CLAUDE.md bus 1; US-025, US-026, US-027).

- `encrypt(data_class, plaintext, aad) -> str` y `decrypt(blob, aad) -> bytes` (US-025):
  síncronas (solo CPU con la DEK en memoria) para usarse desde los tipos de columna de
  US-028. `aad` es `aad_for(record_id)`: el UUID en texto canónico (ADR-002).
- `blind_index(data_class, value) -> str` (US-026): HMAC-SHA-256 hexadecimal del valor
  normalizado con la llave `index` activa de la clase.
- `digest(data) -> str` (N-06): SHA-256 sin llave, de `digest.py`.
- `sign` y `verify` llegan en US-027 (S1-B6), junto con `batch()` y la bitácora
  `crypto_ops` (US-029).

Quien llama nunca elige llave ni algoritmo. El bus no expone ningún método que devuelva una
DEK. Sin keyring cargado (`ensure_keys`), toda operación lanza `crypto_unavailable`.
"""

from __future__ import annotations

import os
from uuid import UUID

from app.core.crypto.aead import open_, seal
from app.core.crypto.blob import NONCE_LEN, format_blob, parse_blob
from app.core.crypto.digest import sha256_hex
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import current_keyring
from app.core.crypto.mac import hmac_sha256_hex
from app.core.crypto.normalize import normalize_for_index
from app.core.crypto.registry import get_spec

digest = sha256_hex
ALG_V01 = "A256GCM"


def aad_for(record_id: UUID) -> bytes:
    """AAD de un registro: su UUID en minúsculas con guiones (forma canónica, ADR-002)."""
    return str(record_id).lower().encode("ascii")


def encrypt(data_class: str, plaintext: bytes, aad: bytes) -> str:
    spec = get_spec(data_class)
    if not spec.encrypt:
        raise CryptoError("unsupported", f"la clase {data_class} no se cifra")
    llave = current_keyring().active_for("encrypt", data_class)
    nonce = os.urandom(NONCE_LEN)
    return format_blob(llave.key_id, ALG_V01, nonce, seal(llave.material, nonce, plaintext, aad))


def decrypt(blob: str, aad: bytes) -> bytes:
    partes = parse_blob(blob)
    llave = current_keyring().get(partes.key_id)
    if llave is None:
        raise CryptoError("key_missing", "el blob usa una llave que este proceso no conoce")
    if llave.state == "retired":
        raise CryptoError("key_retired", "el blob está cifrado con una llave retirada")
    return open_(llave.material, partes.nonce, partes.ciphertext, aad)


def blind_index(data_class: str, value: str) -> str:
    spec = get_spec(data_class)
    if spec.index_kind is None:
        raise CryptoError("no_index", f"la clase {data_class} no tiene índice ciego")
    normalizado = normalize_for_index(value, spec.index_kind)
    llave = current_keyring().active_for("index", data_class)
    return hmac_sha256_hex(llave.material, normalizado.encode("utf-8"))
