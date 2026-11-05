"""Verificación de firmas `minisign` en Python (S5-D72, H-1; S5-B13).

Formato (minisign 0.12): llave pública `RW` + base64(`Ed` + id de 8 bytes + Ed25519 de 32 bytes);
firma `RU`/`RW` + base64(algoritmo + id + Ed25519 de 64 bytes) con `ED` (Ed25519 sobre BLAKE2b-512
del dato), más un comentario de confianza cuya firma global cubre `firma64 || comentario`. El `Ed`
heredado (dato crudo) se rechaza (S5-D72); el comentario de no confianza no está firmado.

Solo `app.core.crypto.bus` lo importa: `bus.verify_signed_manifest` es la única puerta pública y
vive aquí porque `cryptography` y `hashlib` solo se importan dentro de `core/crypto`. Nada de lo
que se verifica es secreto: no hay llaves del keyring ni `crypto_ops`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ALG_PUBLIC: Final = b"Ed"
ALG_PREHASHED: Final = b"ED"
KEY_ID_LEN: Final = 8
PUBKEY_RAW_LEN: Final = 2 + KEY_ID_LEN + 32
SIG_RAW_LEN: Final = 2 + KEY_ID_LEN + 64
GLOBAL_SIG_LEN: Final = 64
UNTRUSTED_PREFIX: Final = "untrusted comment:"
TRUSTED_PREFIX: Final = "trusted comment: "
MAX_SIGNED_BYTES: Final = 1 << 20
MAX_SIGNATURE_BYTES: Final = 4096


@dataclass(frozen=True)
class MinisignKey:
    """Llave pública minisign: `key_id` (8 bytes) y la Ed25519 cruda (32 bytes)."""

    key_id: bytes
    public: bytes


def _decode(texto: str, largo: int) -> bytes:
    crudo = base64.b64decode(texto.strip(), validate=True)
    if len(crudo) != largo:
        raise ValueError("largo inesperado")
    return crudo


def parse_pubkey(text: str) -> MinisignKey:
    """La llave de una línea `RW...` o de un archivo `.pub` completo; `ValueError` si no cabe."""
    lineas = [linea.strip() for linea in text.strip().splitlines() if linea.strip()]
    if len(lineas) == 2 and lineas[0].startswith(UNTRUSTED_PREFIX):
        lineas = lineas[1:]
    if len(lineas) != 1:
        raise ValueError("no es una llave pública minisign")
    try:
        crudo = _decode(lineas[0], PUBKEY_RAW_LEN)
    except (binascii.Error, ValueError) as error:
        raise ValueError("no es una llave pública minisign") from error
    if crudo[:2] != ALG_PUBLIC:
        raise ValueError("algoritmo de llave pública no soportado")
    return MinisignKey(key_id=crudo[2 : 2 + KEY_ID_LEN], public=crudo[2 + KEY_ID_LEN :])


def _ed25519_ok(public: bytes, firma: bytes, mensaje: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(firma, mensaje)
    except (InvalidSignature, ValueError):
        return False
    return True


def _lineas_de_firma(sig_text: str) -> tuple[bytes, bytes, bytes] | None:
    """`(firma 74 bytes, comentario de confianza, firma global)` o `None` si está malformada."""
    # Forma estricta (S5-D177): exactamente cuatro líneas, salto final opcional y sin `\r`.
    lineas = sig_text.split("\n")
    if len(lineas) == 5 and lineas[4] == "":
        lineas = lineas[:4]
    if len(lineas) != 4 or "\r" in sig_text or not lineas[0].startswith(UNTRUSTED_PREFIX):
        return None
    if not lineas[2].startswith(TRUSTED_PREFIX):
        return None
    try:
        firma = _decode(lineas[1], SIG_RAW_LEN)
        global_sig = _decode(lineas[3], GLOBAL_SIG_LEN)
        comentario = lineas[2][len(TRUSTED_PREFIX) :].encode("utf-8")
    except (binascii.Error, ValueError):
        return None
    return firma, comentario, global_sig


def verify_minisign(key: MinisignKey, data: bytes, sig_text: str) -> bool:
    """`True` solo si la firma `ED` de `data` y la del comentario de confianza son de `key`.
    Nunca lanza: una firma malformada, de otra llave o con el algoritmo `Ed` da `False`."""
    try:
        partes = _lineas_de_firma(sig_text)
        if partes is None:
            return False
        firma, comentario, global_sig = partes
        algoritmo, ident, ed = firma[:2], firma[2 : 2 + KEY_ID_LEN], firma[2 + KEY_ID_LEN :]
        if algoritmo != ALG_PREHASHED or ident != key.key_id:
            return False
        resumen = hashlib.blake2b(data, digest_size=64).digest()
        return _ed25519_ok(key.public, ed, resumen) and _ed25519_ok(
            key.public, global_sig, ed + comentario
        )
    except (ValueError, TypeError):
        return False


def _read_regular(path: Path, limit: int) -> bytes | None:
    """Los bytes de un archivo regular, sin seguir enlaces, de como mucho `limit` bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)  # un FIFO no debe colgar el hilo en el `open`
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):  # Windows no tiene O_NOFOLLOW
            return None
        with os.fdopen(os.open(path, flags), "rb") as archivo:
            if not stat.S_ISREG(os.fstat(archivo.fileno()).st_mode):
                return None
            contenido = archivo.read(limit + 1)
    except OSError:
        return None
    return contenido if len(contenido) <= limit else None


def verified_file_bytes(path: Path, pubkey: str) -> bytes | None:
    """Los bytes de `path`, leídos UNA vez, si `<path>.minisig` es una firma válida de ellos con
    `pubkey`; `None` en cualquier otro caso. Nunca lanza (S5-D178: no se vuelve a abrir)."""
    try:
        key = parse_pubkey(pubkey)
        datos = _read_regular(path, MAX_SIGNED_BYTES)
        firma = _read_regular(path.with_name(path.name + ".minisig"), MAX_SIGNATURE_BYTES)
        if datos is None or firma is None:
            return None
        return datos if verify_minisign(key, datos, firma.decode("utf-8")) else None
    except (ValueError, OSError):
        return None


def verify_signed_file(path: Path, pubkey: str) -> bool:
    """`<path>.minisig` es una firma válida de `path` con `pubkey`; nunca lanza."""
    return verified_file_bytes(path, pubkey) is not None
