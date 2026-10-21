"""`format_blob` y `parse_blob` (US-025 T8): cinco partes, prefijo `apx1`, base64url sin relleno."""

from __future__ import annotations

import base64
from uuid import UUID, uuid4

import pytest

from app.core.crypto.blob import BLOB_PREFIX, BlobParts, format_blob, parse_blob
from app.core.crypto.errors import CryptoError

NONCE = bytes(range(12))
CT = b"\xff\x00cifrado-con-etiqueta-de-16-bytes"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def test_ida_y_vuelta() -> None:
    key_id = uuid4()
    blob = format_blob(key_id, "A256GCM", NONCE, CT)
    partes = blob.split(".")
    assert len(partes) == 5
    assert partes[0] == BLOB_PREFIX == "apx1"
    assert partes[1] == str(key_id) and partes[2] == "A256GCM"
    assert "=" not in blob and "+" not in blob and "/" not in blob
    assert parse_blob(blob) == BlobParts("apx1", key_id, "A256GCM", NONCE, CT)


def _blob(**cambios: str) -> str:
    partes = {
        "p": "apx1",
        "k": "11111111-2222-3333-4444-555555555555",
        "a": "A256GCM",
        "n": _b64(NONCE),
        "c": _b64(CT),
    }
    partes.update(cambios)
    return ".".join(partes.values())


@pytest.mark.parametrize(
    "blob",
    [
        _blob().rsplit(".", 1)[0],  # cuatro partes
        _blob() + ".extra",  # seis partes
        _blob(p="apx2"),
        _blob(a="DES"),
        _blob(c="no*base64!"),
        _blob(n=_b64(NONCE[:11])),
        _blob(k="no-es-uuid"),
        "",
        "apx1",
    ],
    ids=["4-partes", "6-partes", "apx2", "DES", "b64", "nonce-11", "uuid", "vacio", "solo-prefijo"],
)
def test_parse_rechaza_blobs_invalidos(blob: str) -> None:
    with pytest.raises(CryptoError) as excinfo:
        parse_blob(blob)
    assert excinfo.value.code == "blob_invalid"
    assert _b64(CT) not in str(excinfo.value)
    assert blob == "" or blob not in str(excinfo.value)


def test_key_id_en_minusculas() -> None:
    blob = format_blob(UUID("ABCDEF01-0000-0000-0000-000000000000"), "A256GCM", NONCE, CT)
    assert blob.split(".")[1] == "abcdef01-0000-0000-0000-000000000000"
