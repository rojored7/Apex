"""La única puerta del bus de criptografía (CLAUDE.md bus 1; US-025 a US-029).

- `encrypt(data_class, plaintext, aad, *, record_id=None) -> str` y
  `decrypt(blob, aad, *, purpose=None, record_id=None) -> bytes` (US-025): síncronas
  (solo CPU con la DEK en memoria) para usarse desde los tipos de columna de US-028.
  `aad` es `aad_for(record_id)`: el UUID en texto canónico (ADR-002).
- `blind_index(data_class, value, *, record_id=None) -> str` (US-026): HMAC-SHA-256 del
  valor normalizado con la llave `index` activa de la clase.
- `sign(data_class, data) -> str` y `verify(data_class, data, signature) -> bool`
  (US-027): `async`, delegan en el `KeyProvider`; la privada nunca sale del proveedor.
  `verify` acepta llaves `active`, `decrypt_only` y `retired` (Q27).
- `digest(data) -> str` (N-06): SHA-256 sin llave; no deja fila en `crypto_ops`.
- `batch(verb, data_class)` (US-029): agrupa las operaciones de un lote en una fila.

Cada operación con llave llama a `oplog.record`; el propósito del descifrado (`mask`,
`reveal`, `notify`, `auth_link`, `export`) y el `record_id` son argumentos con nombre. Quien
llama nunca elige llave ni algoritmo. El bus no expone ningún método que devuelva una DEK.
Sin keyring cargado (`ensure_keys`), toda operación lanza `crypto_unavailable`.
"""

from __future__ import annotations

import os
from uuid import UUID

from app.core.crypto import oplog
from app.core.crypto.aead import open_, seal
from app.core.crypto.blob import NONCE_LEN, format_blob, parse_blob
from app.core.crypto.digest import sha256_hex
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import LoadedKey, current_keyring
from app.core.crypto.mac import hmac_sha256_hex
from app.core.crypto.normalize import normalize_for_index
from app.core.crypto.provider import KeyProvider, current_provider
from app.core.crypto.registry import get_spec
from app.core.crypto.signature import format_signature, parse_signature

digest = sha256_hex
batch = oplog.batch
ALG_V01 = "A256GCM"
SIGN_ALG_V01 = "Ed25519"


def aad_for(record_id: UUID) -> bytes:
    """AAD de un registro: su UUID en minúsculas con guiones (forma canónica, ADR-002)."""
    return str(record_id).lower().encode("ascii")


def _record_id_from_aad(aad: bytes, record_id: UUID | None) -> UUID | None:
    if record_id is not None:
        return record_id
    try:
        return UUID(aad.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None


def encrypt(data_class: str, plaintext: bytes, aad: bytes, *, record_id: UUID | None = None) -> str:
    spec = get_spec(data_class)
    if not spec.encrypt:
        raise CryptoError("unsupported", f"la clase {data_class} no se cifra")
    llave = current_keyring().active_for("encrypt", data_class)
    nonce = os.urandom(NONCE_LEN)
    blob = format_blob(llave.key_id, ALG_V01, nonce, seal(llave.material, nonce, plaintext, aad))
    oplog.record(
        "encrypt",
        data_class=data_class,
        key_id=llave.key_id,
        key_version=llave.version,
        record_id=_record_id_from_aad(aad, record_id),
    )
    return blob


def decrypt(
    blob: str, aad: bytes, *, purpose: str | None = None, record_id: UUID | None = None
) -> bytes:
    partes = parse_blob(blob)
    llave = current_keyring().get(partes.key_id)
    if llave is None:
        raise CryptoError("key_missing", "el blob usa una llave que este proceso no conoce")
    if llave.state == "retired":
        raise CryptoError("key_retired", "el blob está cifrado con una llave retirada")
    quien = _record_id_from_aad(aad, record_id)
    try:
        claro = open_(llave.material, partes.nonce, partes.ciphertext, aad)
    except CryptoError:
        oplog.record(
            "decrypt",
            data_class=llave.data_class,
            key_id=llave.key_id,
            key_version=llave.version,
            record_id=quien,
            purpose=purpose,
            result="error",
        )
        raise
    oplog.record(
        "decrypt",
        data_class=llave.data_class,
        key_id=llave.key_id,
        key_version=llave.version,
        record_id=quien,
        purpose=purpose,
    )
    return claro


def blind_index(data_class: str, value: str, *, record_id: UUID | None = None) -> str:
    spec = get_spec(data_class)
    if spec.index_kind is None:
        raise CryptoError("no_index", f"la clase {data_class} no tiene índice ciego")
    normalizado = normalize_for_index(value, spec.index_kind)
    llave = current_keyring().active_for("index", data_class)
    indice = hmac_sha256_hex(llave.material, normalizado.encode("utf-8"))
    oplog.record(
        "index",
        data_class=data_class,
        key_id=llave.key_id,
        key_version=llave.version,
        record_id=record_id,
    )
    return indice


def _key_ref(llave: LoadedKey) -> str:
    """Las llaves `sign` guardan la referencia del proveedor, no material (US-027)."""
    return bytes(llave.material).decode("ascii")


def _provider() -> KeyProvider:
    """El proveedor con el que se cargó el keyring (o el del proceso)."""
    return current_keyring().provider or current_provider()


async def sign(data_class: str, data: bytes) -> str:
    spec = get_spec(data_class)
    if not spec.sign:
        raise CryptoError("unsupported", f"la clase {data_class} no se firma")
    llave = current_keyring().active_for("sign", data_class)
    firma = await _provider().sign(_key_ref(llave), data)
    oplog.record("sign", data_class=data_class, key_id=llave.key_id, key_version=llave.version)
    return format_signature(llave.key_id, SIGN_ALG_V01, firma)


async def verify(data_class: str, data: bytes, signature: str) -> bool:
    partes = parse_signature(signature)
    llave = current_keyring().get(partes.key_id)
    if llave is None or llave.purpose != "sign" or llave.data_class != data_class:
        raise CryptoError("key_missing", "la firma no corresponde a una llave de esta clase")
    valida = await _provider().verify(_key_ref(llave), data, partes.sig)
    oplog.record(
        "verify",
        data_class=data_class,
        key_id=llave.key_id,
        key_version=llave.version,
        result="ok" if valida else "error",
    )
    return valida
