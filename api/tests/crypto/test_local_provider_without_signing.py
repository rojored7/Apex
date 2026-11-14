"""`LocalFileProvider` sin ruta de firma: el api nunca lee la semilla (S7-D4, S7-D23, M-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cli import init_keys_files, key_paths_in
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import SIGNING_KEY_REF, LocalFileProvider


def _sin_firma(tmp_path: Path) -> tuple[LocalFileProvider, Path]:
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    return LocalFileProvider(rutas.kek, None), rutas.signing_key


def test_sin_ruta_de_firma_no_lee_la_semilla(tmp_path: Path) -> None:
    """Se construye aunque la semilla no exista: nunca la abre."""
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.signing_key.unlink()

    proveedor = LocalFileProvider(rutas.kek, None)

    assert proveedor.name == "local"


async def test_sign_lanza_sign_unavailable(tmp_path: Path) -> None:
    proveedor, _ = _sin_firma(tmp_path)

    with pytest.raises(CryptoError) as excinfo:
        await proveedor.sign(SIGNING_KEY_REF, b"datos")

    assert excinfo.value.code == "sign_unavailable"


async def test_sign_public_key_lanza_sign_unavailable(tmp_path: Path) -> None:
    proveedor, _ = _sin_firma(tmp_path)

    with pytest.raises(CryptoError) as excinfo:
        await proveedor.sign_public_key()

    assert excinfo.value.code == "sign_unavailable"


async def test_verify_y_key_info_tampoco_tienen_semilla(tmp_path: Path) -> None:
    proveedor, _ = _sin_firma(tmp_path)

    with pytest.raises(CryptoError) as v:
        await proveedor.verify(SIGNING_KEY_REF, b"d", b"\x00" * 64)
    with pytest.raises(CryptoError) as k:
        await proveedor.key_info(SIGNING_KEY_REF)

    assert (v.value.code, k.value.code) == ("sign_unavailable", "sign_unavailable")


async def test_wrap_y_unwrap_siguen_con_la_kek(tmp_path: Path) -> None:
    proveedor, _ = _sin_firma(tmp_path)
    dek = b"d" * 32

    envuelta = await proveedor.wrap(dek)

    assert await proveedor.unwrap(envuelta) == dek
    assert await proveedor.status() == "ok"
    assert proveedor.sign_key_ref() == SIGNING_KEY_REF
