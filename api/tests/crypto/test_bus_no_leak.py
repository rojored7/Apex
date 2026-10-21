"""Ni el texto en claro ni la DEK llegan a logs, keyring ni excepciones (US-025 T12)."""

from __future__ import annotations

import base64
import logging
from uuid import uuid4

import pytest

from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import Keyring

CLARO = "1020304-secreto-ñ"


def _formas(data: bytes) -> list[str]:
    return [data.hex(), base64.b64encode(data).decode(), base64.urlsafe_b64encode(data).decode()]


def test_sin_fugas_en_logs_ni_errores(bus_listo: Keyring, caplog: pytest.LogCaptureFixture) -> None:
    aad = bus.aad_for(uuid4())
    with caplog.at_level(logging.DEBUG):
        blob = bus.encrypt("member.document", CLARO.encode(), aad)
        assert bus.decrypt(blob, aad).decode() == CLARO
        with pytest.raises(CryptoError) as excinfo:
            bus.decrypt(blob, bus.aad_for(uuid4()))
        bus.blind_index("member.document", CLARO)
    texto = caplog.text + str(excinfo.value) + repr(excinfo.value)
    assert CLARO not in texto
    assert blob not in str(excinfo.value)
    for llave in bus_listo.keys():
        for forma in _formas(bytes(llave.material)):
            assert forma not in texto
            assert forma not in repr(bus_listo) and forma not in repr(llave)
    assert "material" not in repr(bus_listo) and "bytearray" not in repr(bus_listo)


def test_el_keyring_no_expone_las_dek_como_bytes(bus_listo: Keyring) -> None:
    llave = bus_listo.active_for("encrypt", "member.document")
    assert isinstance(llave.material, bytearray)
    assert not [n for n in dir(bus_listo) if n.lower().startswith(("dek", "material", "kek"))]
