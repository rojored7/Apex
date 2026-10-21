"""`LocalFileProvider`: KEK y llave de firma en archivos del volumen `keys` (US-023; N-03).

- KEK: 32 bytes crudos en `CRYPTO_LOCAL_KEK_PATH`, modo 600, fuera del repo y de la imagen.
- Envoltura de una DEK: `b"apxw1" || nonce(12) || AES-256-GCM(kek, nonce, dek, aad)` con
  `aad = b"apx-dek-wrap"`. El prefijo autodescribe la envoltura (ADR-002); `algorithm` en
  `crypto_keys` describe la llave envuelta, no la envoltura.
- Firma del bus: Ed25519 con semilla cruda de 32 bytes en `CRYPTO_LOCAL_SIGNING_KEY_PATH`.
- `rotate` de la KEK local no existe en v0.1 (la rotación de DEK es US-030).
- La KEK nunca sale de esta clase: no hay accesor público y ni `repr` ni las excepciones
  llevan bytes. En Windows (NTFS) no hay modo POSIX, así que la comprobación de permisos
  solo corre fuera de `nt`; en los contenedores Linux es obligatoria.
"""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.crypto.errors import CryptoError
from app.core.crypto.provider import KeyInfo

WRAP_PREFIX: Final = b"apxw1"
NONCE_LEN: Final = 12
TAG_LEN: Final = 16
KEK_LEN: Final = 32
SEED_LEN: Final = 32
WRAP_AAD: Final = b"apx-dek-wrap"
SIGNING_KEY_REF: Final = "local:sign-ed25519"
PROVIDER_NAME: Final = "local"


def parse_wrapped(wrapped: bytes) -> tuple[bytes, bytes]:
    """`(nonce, ciphertext)` de una envoltura `apxw1`; pura, sin primitivas."""
    if not wrapped.startswith(WRAP_PREFIX):
        raise CryptoError("unwrap_failed", "la envoltura no tiene el prefijo apxw1")
    cuerpo = wrapped[len(WRAP_PREFIX) :]
    if len(cuerpo) < NONCE_LEN + TAG_LEN:
        raise CryptoError("unwrap_failed", "la envoltura es demasiado corta")
    return cuerpo[:NONCE_LEN], cuerpo[NONCE_LEN:]


def check_key_file(path: Path, *, size: int, name: str) -> None:
    """Existe, es archivo regular, modo sin permisos de grupo/otros y tamaño exacto.

    Nunca lee ni imprime el contenido.
    """
    try:
        st = path.stat()
    except FileNotFoundError:
        raise CryptoError("kek_missing", f"{name} no encontrada en {path}") from None
    if not stat.S_ISREG(st.st_mode):
        raise CryptoError("kek_invalid", f"{name} no es un archivo regular: {path}")
    if os.name != "nt" and stat.S_IMODE(st.st_mode) & 0o077:
        raise CryptoError(
            "kek_insecure_permissions",
            f"permisos de la {name} inseguros en {path}: debe ser 600",
        )
    if st.st_size != size:
        raise CryptoError("kek_invalid", f"{name} con tamaño incorrecto en {path}")


class LocalFileProvider:
    """`KeyProvider` de v0.1. Carga la KEK y la semilla de firma en memoria al construirse."""

    def __init__(self, kek_path: Path, signing_key_path: Path) -> None:
        check_key_file(kek_path, size=KEK_LEN, name="KEK")
        check_key_file(signing_key_path, size=SEED_LEN, name="llave de firma")
        self._aead = AESGCM(kek_path.read_bytes())
        self._signing = Ed25519PrivateKey.from_private_bytes(signing_key_path.read_bytes())
        self._signing_created_at = datetime.fromtimestamp(signing_key_path.stat().st_mtime, UTC)

    def __repr__(self) -> str:
        return "LocalFileProvider()"

    async def wrap(self, dek: bytes) -> bytes:
        nonce = os.urandom(NONCE_LEN)
        return WRAP_PREFIX + nonce + self._aead.encrypt(nonce, dek, WRAP_AAD)

    async def unwrap(self, wrapped: bytes) -> bytes:
        nonce, cifrado = parse_wrapped(wrapped)
        try:
            return self._aead.decrypt(nonce, cifrado, WRAP_AAD)
        except InvalidTag:
            raise CryptoError("unwrap_failed", "la envoltura no se abre con esta KEK") from None

    def _require_signing_ref(self, key_ref: str) -> None:
        if key_ref != SIGNING_KEY_REF:
            raise CryptoError("key_missing", f"el proveedor local no tiene la llave {key_ref}")

    async def sign(self, key_ref: str, data: bytes) -> bytes:
        self._require_signing_ref(key_ref)
        return self._signing.sign(data)

    async def verify(self, key_ref: str, data: bytes, signature: bytes) -> bool:
        self._require_signing_ref(key_ref)
        try:
            self._signing.public_key().verify(signature, data)
        except InvalidSignature:
            return False
        return True

    async def rotate(self, key_ref: str) -> KeyInfo:
        raise CryptoError("unsupported", "el proveedor local no rota llaves en v0.1")

    async def key_info(self, key_ref: str) -> KeyInfo:
        self._require_signing_ref(key_ref)
        return KeyInfo(
            key_ref=SIGNING_KEY_REF,
            algorithm="Ed25519",
            provider=PROVIDER_NAME,
            version=1,
            created_at=self._signing_created_at,
        )
