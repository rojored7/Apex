"""La única puerta del bus de criptografía (CLAUDE.md bus 1; US-025 a US-029).

- `encrypt(data_class, plaintext, aad, *, record_id=None) -> str` y
  `decrypt(blob, aad, *, purpose=None, record_id=None) -> bytes` (US-025): síncronas
  (solo CPU con la DEK en memoria) para usarse desde los tipos de columna de US-028.
  `aad` es `aad_for(record_id)`: el UUID en texto canónico (ADR-002).
- `blind_index(data_class, value, *, record_id=None) -> str` (US-026): HMAC-SHA-256 del
  valor normalizado con la llave `index` activa de la clase.
- `sign(data_class, data) -> str` (US-027): `async`, delega en el `KeyProvider`; la privada nunca
  sale del proveedor. La firma lleva el algoritmo de la FILA de la llave (S6-D40).
- `verify(data_class, data, signature) -> bool` (S6-D62, D81): verifica en proceso con
  `crypto_keys.public_key` de la fila del `key_id`, sin llamar al proveedor; acepta llaves
  `active`, `decrypt_only` y `retired` (Q27). `ML-DSA-65` da `unsupported` hasta EP-26.
- `digest(data) -> str` (N-06): SHA-256 sin llave; no deja fila en `crypto_ops`.
- `batch(verb, data_class)` (US-029): agrupa las operaciones de un lote en una fila.

Cada operación con llave llama a `oplog.record`; el propósito del descifrado (`mask`,
`reveal`, `notify`, `auth_link`, `export`) y el `record_id` son argumentos con nombre. Quien
llama nunca elige llave ni algoritmo. El bus no expone ningún método que devuelva una DEK.
Sin keyring cargado (`ensure_keys`), toda operación lanza `crypto_unavailable`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import UUID

from app.core.crypto import minisign, oplog
from app.core.crypto.aead import open_, seal
from app.core.crypto.blob import NONCE_LEN, format_blob, parse_blob
from app.core.crypto.digest import sha256_hex
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import LoadedKey, current_keyring
from app.core.crypto.mac import hmac_sha256_hex
from app.core.crypto.normalize import normalize_for_index
from app.core.crypto.provider import KeyProvider
from app.core.crypto.registry import get_spec
from app.core.crypto.signature import format_signature, parse_signature, verify_ed25519

digest = sha256_hex
batch = oplog.batch
ALG_V01 = "A256GCM"
SIGN_ALG_ED25519 = "Ed25519"
_REF_LOCAL = "local:sign-ed25519"
_REF_OPENBAO = re.compile(r"^apex-sign-audit[a-z0-9-]*$")


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
    """Las llaves `sign` guardan la referencia del proveedor, no material (US-027). Se valida
    antes de usarla (M-2b): `local:sign-ed25519` con `local`, `^apex-sign-audit[a-z0-9-]*$` con
    OpenBao; nada más (ni la KEK ni una ruta)."""
    try:
        referencia = bytes(llave.material).decode("ascii")
    except UnicodeDecodeError:
        raise CryptoError(
            "bad_key_ref", "la referencia de la llave de firma no es válida"
        ) from None
    valida = (
        referencia == _REF_LOCAL
        if llave.provider == "local"
        else _REF_OPENBAO.fullmatch(referencia) is not None
    )
    if not valida:
        raise CryptoError("bad_key_ref", "la referencia de la llave de firma no es válida")
    return referencia


def _provider(llave: LoadedKey) -> KeyProvider:
    """El proveedor de la fila de la llave (S5-D3); `local` solo se construye si se pide."""
    return current_keyring().provider_for(llave.provider)


async def sign(data_class: str, data: bytes) -> str:
    spec = get_spec(data_class)
    if not spec.sign:
        raise CryptoError("unsupported", f"la clase {data_class} no se firma")
    llave = current_keyring().active_for("sign", data_class)
    if llave.algorithm != SIGN_ALG_ED25519:
        raise CryptoError("unsupported", f"algoritmo de firma no soportado: {llave.algorithm}")
    firma = await _provider(llave).sign(_key_ref(llave), data)
    # Autoverificación (S6, H1): la firma debe verificar con la clave pública de la FILA. Si el
    # proveedor rotó fuera del flujo (otra llave Transit, otra semilla local) no se entrega.
    if llave.public_key is None or not verify_ed25519(llave.public_key, data, firma):
        oplog.record(
            "sign",
            data_class=data_class,
            key_id=llave.key_id,
            key_version=llave.version,
            result="error",
        )
        raise CryptoError(
            "signature_unverifiable",
            "la firma no verifica con la clave pública guardada de la llave",
        )
    oplog.record("sign", data_class=data_class, key_id=llave.key_id, key_version=llave.version)
    return format_signature(llave.key_id, llave.algorithm, firma)


async def verify(data_class: str, data: bytes, signature: str) -> bool:
    partes = parse_signature(signature)
    llave = current_keyring().get(partes.key_id)
    if llave is None or llave.purpose != "sign" or llave.data_class != data_class:
        raise CryptoError("key_missing", "la firma no corresponde a una llave de esta clase")
    if SIGN_ALG_ED25519 != partes.alg or llave.algorithm != SIGN_ALG_ED25519:
        raise CryptoError("unsupported", f"algoritmo de firma no soportado: {partes.alg}")
    if llave.public_key is None:
        raise CryptoError("key_missing", "la llave de firma no tiene clave pública")
    valida = verify_ed25519(llave.public_key, data, partes.sig)
    oplog.record(
        "verify",
        data_class=data_class,
        key_id=llave.key_id,
        key_version=llave.version,
        result="ok" if valida else "error",
    )
    return valida


def verify_signed_manifest(path: Path, pubkey: str) -> bool:
    """`True` si `<path>.minisig` es una firma minisign válida de `path` con `pubkey` (S5-D72).

    Única puerta pública de la verificación `minisign`; sin llave del keyring ni `crypto_ops`.
    Nunca lanza: archivo ausente, enlace simbólico, mayor de 1 MiB o firma mala dan `False`.
    """
    return minisign.verify_signed_file(path, pubkey)


def verified_manifest_bytes(path: Path, pubkey: str) -> bytes | None:
    """Los bytes de `path` si su firma `minisign` es válida con `pubkey`; `None` si no (S5-D178).

    El archivo se abre UNA vez: quien parsea esos bytes no vuelve a leerlo, así no hay ventana entre
    la firma y el uso. Mismas negativas que `verify_signed_manifest`; nunca lanza.
    """
    return minisign.verified_file_bytes(path, pubkey)
