"""Tercera puerta de cifrado y descifrado (S6-C1; S6-D53, S6-D60).

Única que importa `bus` en el módulo; el nombre de las funciones lo fija
`tests/architecture/test_reveal_single_door.py`. El blob textual `apx1.…` se guarda en el objeto
del almacenamiento (no hay columna): `aad = aad_for(id de la fila)`, así un objeto copiado sobre
otra fila no se abre.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final
from uuid import UUID

from app.core.crypto import bus
from app.core.crypto.errors import CryptoError

DATA_CLASS: Final = "attachment.sensitive"


def _encrypt_file(data: bytes, attachment_id: UUID) -> bytes:
    """Blob `apx1.…` (ASCII) del contenido, con la llave activa de la clase."""
    blob = bus.encrypt(DATA_CLASS, data, bus.aad_for(attachment_id), record_id=attachment_id)
    return blob.encode("ascii")


def _decrypt_file(blob: bytes, attachment_id: UUID) -> bytes:
    """Contenido en claro; falla con `CryptoError` si el blob no es de esa fila o está corrupto."""
    try:
        texto = blob.decode("ascii")
    except UnicodeDecodeError:  # objeto corrupto o sobrescrito: nunca un 500 (revisión de C1)
        raise CryptoError("blob_invalid", "el objeto no es un blob apx1") from None
    return bus.decrypt(texto, bus.aad_for(attachment_id), record_id=attachment_id)


def _reencrypt_blob(blob: bytes, attachment_id: UUID) -> bytes:
    """Descifra con la llave del propio blob (`decrypt_only` incluida) y cifra con la activa."""
    return _encrypt_file(_decrypt_file(blob, attachment_id), attachment_id)


def blob_key_id(blob: bytes) -> UUID:
    """`key_id` que declara el blob `apx1.<key_id>.…` (sin descifrar nada)."""
    return UUID(blob.split(b".", 2)[1].decode("ascii"))


def peek_key_id(head: bytes) -> UUID | None:
    """`key_id` de los primeros bytes de un blob en reposo; `None` si no es una cabecera `apx1`."""
    partes = head.split(b".", 2)
    if len(partes) < 3 or partes[0] != b"apx1":
        return None
    try:
        return UUID(partes[1].decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None


@contextmanager
def batch() -> Iterator[Any]:
    """Un lote de `crypto_ops`: todo el recifrado comparte el mismo `batch_id`."""
    with bus.batch("rotate", DATA_CLASS) as handle:
        yield handle
