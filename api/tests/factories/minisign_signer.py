"""Firmante `minisign` de prueba (S5-B13, Rojo): llaves desechables generadas en el arnés.

Escribe el mismo formato que `minisign -S` (0.12): `ED` (Ed25519 sobre BLAKE2b-512 del dato) o el
`Ed` heredado (dato crudo), y el comentario de confianza firmado con la misma llave. Las llaves se
derivan de una semilla fija de PRUEBA (no secreta, sin valor fuera de estas pruebas) para que los
fallos se reproduzcan. El formato se contrastó una vez contra el binario real (`minisign -V` dentro
de `apex-backup:local`); los vectores de `tests/crypto/_minisign_vectors.py` son de ese binario.
`cryptography` y `hashlib` están prohibidos fuera de `core/crypto`: aquí van con `noqa` como en
`tests/factories/fake_transit.py`.
"""

from __future__ import annotations

import base64
import hashlib  # noqa: TID251 - firmante de prueba; el api verifica por core.crypto.bus
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization  # noqa: TID251
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: TID251

UNTRUSTED = "untrusted comment: signature from minisign secret key"
TRUSTED_DEFAULT = "timestamp:1700000000\tfile:latest.json"


@dataclass(frozen=True)
class SigningKey:
    """Llave de prueba: `pubkey` es la línea `RW...` (lo que va en `BACKUP_SIGN_PUBKEY`)."""

    private: Ed25519PrivateKey
    key_id: bytes
    public: bytes
    pubkey: str

    @property
    def pubkey_file(self) -> str:
        ident = self.key_id[::-1].hex().upper()
        return f"untrusted comment: minisign public key {ident}\n{self.pubkey}\n"


def make_signing_key(seed: int = 1) -> SigningKey:
    """Llave determinista por `seed` (1 a 255)."""
    privada = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    publica = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = bytes([seed ^ 0x5A]) * 8
    return SigningKey(
        private=privada,
        key_id=key_id,
        public=publica,
        pubkey=base64.b64encode(b"Ed" + key_id + publica).decode("ascii"),
    )


def sign_bytes(
    key: SigningKey, data: bytes, *, trusted_comment: str = TRUSTED_DEFAULT, legacy: bool = False
) -> str:
    """Contenido de un `.minisig` de `data`; `legacy=True` firma el dato crudo con `Ed`."""
    mensaje = data if legacy else hashlib.blake2b(data, digest_size=64).digest()
    firma = key.private.sign(mensaje)
    algoritmo = b"Ed" if legacy else b"ED"
    linea = base64.b64encode(algoritmo + key.key_id + firma).decode("ascii")
    global_sig = key.private.sign(firma + trusted_comment.encode("utf-8"))
    return (
        f"{UNTRUSTED}\n{linea}\ntrusted comment: {trusted_comment}\n"
        f"{base64.b64encode(global_sig).decode('ascii')}\n"
    )


def corrupt_signature_line(sig_text: str) -> str:
    """El mismo `.minisig` con un bit cambiado en la firma Ed25519 de la línea 2."""
    lineas = sig_text.split("\n")
    crudo = bytearray(base64.b64decode(lineas[1]))
    crudo[20] ^= 0x01
    lineas[1] = base64.b64encode(bytes(crudo)).decode("ascii")
    return "\n".join(lineas)


def write_signature(key: SigningKey, manifest: Path, *, corrupt: bool = False) -> Path:
    """Escribe `<manifest>.minisig` con la firma del contenido actual de `manifest`."""
    texto = sign_bytes(key, manifest.read_bytes(), trusted_comment=f"file:{manifest.name}")
    if corrupt:
        texto = corrupt_signature_line(texto)
    destino = manifest.with_name(manifest.name + ".minisig")
    destino.write_text(texto, encoding="utf-8", newline="\n")
    return destino
