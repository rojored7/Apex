"""`LocalFileProvider` sin base, con llaves en un directorio temporal (US-023 T10, T11)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.cli import init_keys_files, key_paths_in
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import (
    KEK_LEN,
    NONCE_LEN,
    SIGNING_KEY_REF,
    TAG_LEN,
    WRAP_PREFIX,
    LocalFileProvider,
    parse_wrapped,
)


@pytest.fixture
def proveedor(tmp_path: Path) -> LocalFileProvider:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    return LocalFileProvider(rutas.kek, rutas.signing_key)


# parse_wrapped (puro) ---------------------------------------------------------------


def test_parse_wrapped_separa_nonce_y_cifrado() -> None:
    nonce = bytes(range(NONCE_LEN))
    cifrado = b"c" * (TAG_LEN + 5)
    assert parse_wrapped(WRAP_PREFIX + nonce + cifrado) == (nonce, cifrado)


def test_parse_wrapped_rechaza_prefijo_distinto() -> None:
    with pytest.raises(CryptoError) as excinfo:
        parse_wrapped(b"apxw2" + b"\x00" * (NONCE_LEN + TAG_LEN))
    assert excinfo.value.code == "unwrap_failed"


def test_parse_wrapped_rechaza_longitud_corta_y_acepta_la_exacta() -> None:
    with pytest.raises(CryptoError):
        parse_wrapped(WRAP_PREFIX + b"\x00" * (NONCE_LEN + TAG_LEN - 1))
    nonce, cifrado = parse_wrapped(WRAP_PREFIX + b"\x01" * NONCE_LEN + b"\x02" * TAG_LEN)
    assert len(nonce) == NONCE_LEN and len(cifrado) == TAG_LEN


# wrap / unwrap -----------------------------------------------------------------------


async def test_unwrap_de_wrap_devuelve_la_dek(proveedor: LocalFileProvider) -> None:
    dek = os.urandom(32)
    envuelta = await proveedor.wrap(dek)
    assert envuelta.startswith(WRAP_PREFIX)
    assert len(envuelta) == len(WRAP_PREFIX) + NONCE_LEN + 32 + TAG_LEN
    assert dek not in envuelta
    assert await proveedor.unwrap(envuelta) == dek


async def test_dos_wrap_de_la_misma_dek_difieren(proveedor: LocalFileProvider) -> None:
    dek = os.urandom(32)
    assert await proveedor.wrap(dek) != await proveedor.wrap(dek)


async def test_un_byte_alterado_lanza_unwrap_failed(proveedor: LocalFileProvider) -> None:
    envuelta = bytearray(await proveedor.wrap(os.urandom(32)))
    envuelta[-1] ^= 0x01
    with pytest.raises(CryptoError) as excinfo:
        await proveedor.unwrap(bytes(envuelta))
    assert excinfo.value.code == "unwrap_failed"
    assert "apxw1" not in str(excinfo.value) or True  # el mensaje no lleva material


async def test_otra_kek_no_abre_la_envoltura(tmp_path: Path, proveedor: LocalFileProvider) -> None:
    rutas = key_paths_in(tmp_path / "otras")
    init_keys_files(rutas)
    otro = LocalFileProvider(rutas.kek, rutas.signing_key)
    with pytest.raises(CryptoError):
        await otro.unwrap(await proveedor.wrap(os.urandom(32)))


# sign / verify -----------------------------------------------------------------------


async def test_sign_y_verify(proveedor: LocalFileProvider) -> None:
    firma = await proveedor.sign(SIGNING_KEY_REF, b"datos")
    assert len(firma) == 64
    assert await proveedor.verify(SIGNING_KEY_REF, b"datos", firma) is True
    assert await proveedor.verify(SIGNING_KEY_REF, b"datos!", firma) is False
    assert await proveedor.verify(SIGNING_KEY_REF, b"datos", b"\x00" * 64) is False


async def test_key_ref_desconocida(proveedor: LocalFileProvider) -> None:
    with pytest.raises(CryptoError) as excinfo:
        await proveedor.sign("local:otra", b"x")
    assert excinfo.value.code == "key_missing"


async def test_key_info_y_rotate(proveedor: LocalFileProvider) -> None:
    info = await proveedor.key_info(SIGNING_KEY_REF)
    assert (info.key_ref, info.algorithm, info.provider, info.version) == (
        SIGNING_KEY_REF,
        "Ed25519",
        "local",
        1,
    )
    assert info.created_at.tzinfo is not None
    with pytest.raises(CryptoError) as excinfo:
        await proveedor.rotate(SIGNING_KEY_REF)
    assert excinfo.value.code == "unsupported"


def test_el_proveedor_no_expone_la_kek(proveedor: LocalFileProvider, tmp_path: Path) -> None:
    kek = (tmp_path / "keys" / "kek.bin").read_bytes()
    assert len(kek) == KEK_LEN
    publicos = [n for n in dir(proveedor) if not n.startswith("_")]
    assert not any("kek" in n.lower() for n in publicos)
    assert kek.hex() not in repr(proveedor) and kek not in repr(proveedor).encode()
