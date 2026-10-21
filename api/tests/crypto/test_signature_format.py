"""`format_signature` y `parse_signature`: cuatro partes, `apx1`, base64url (US-027 T5)."""

from __future__ import annotations

import base64
from uuid import uuid4

import pytest

from app.core.crypto.errors import CryptoError
from app.core.crypto.signature import SignatureParts, format_signature, parse_signature

SIG = bytes(range(64))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def test_ida_y_vuelta() -> None:
    key_id = uuid4()
    firma = format_signature(key_id, "Ed25519", SIG)
    partes = firma.split(".")
    assert len(partes) == 4 and partes[0] == "apx1" and partes[2] == "Ed25519"
    assert "=" not in firma
    assert parse_signature(firma) == SignatureParts(key_id, "Ed25519", SIG)


@pytest.mark.parametrize(
    "firma",
    [
        "abc",
        "apx1.11111111-2222-3333-4444-555555555555.Ed25519",
        "apx1.11111111-2222-3333-4444-555555555555.Ed25519." + _b64(SIG) + ".extra",
        "apx2.11111111-2222-3333-4444-555555555555.Ed25519." + _b64(SIG),
        "apx1.11111111-2222-3333-4444-555555555555.RSA." + _b64(SIG),
        "apx1.11111111-2222-3333-4444-555555555555.Ed25519.no*b64!",
        "apx1.no-uuid.Ed25519." + _b64(SIG),
    ],
    ids=["abc", "3-partes", "5-partes", "apx2", "RSA", "b64", "uuid"],
)
def test_parse_rechaza(firma: str) -> None:
    with pytest.raises(CryptoError) as excinfo:
        parse_signature(firma)
    assert excinfo.value.code == "signature_invalid"
    assert _b64(SIG) not in str(excinfo.value)


def test_format_rechaza_algoritmo_desconocido() -> None:
    with pytest.raises(CryptoError):
        format_signature(uuid4(), "RSA", SIG)
