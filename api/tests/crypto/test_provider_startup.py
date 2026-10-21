"""El arranque falla claro sin KEK o con permisos abiertos, y nunca filtra material (US-023 T13)."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import pytest

from app.cli import init_keys_files, key_paths_in
from app.core.config import Settings, load_settings
from app.core.crypto.errors import CryptoError
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider, current_provider, get_key_provider
from app.main import create_app

SOLO_POSIX = pytest.mark.skipif(os.name == "nt", reason="NTFS no conserva el modo POSIX")


def _settings(tmp_path: Path, test_database_url: str, **extra: str) -> Settings:
    rutas = key_paths_in(tmp_path / "keys")
    valores = {
        "DATABASE_URL": test_database_url,
        "JWT_PRIVATE_KEY_PATH": str(rutas.jwt_private),
        "CRYPTO_PROVIDER": "local",
        "CRYPTO_LOCAL_KEK_PATH": str(rutas.kek),
        "CRYPTO_LOCAL_SIGNING_KEY_PATH": str(rutas.signing_key),
        "UPLOADS_DIR": "/data/uploads",
        "CORS_ORIGINS": '["http://localhost"]',
        "ENV": "dev",
        **extra,
    }
    env = tmp_path / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
    return load_settings(env_file=env)


def test_kek_ausente(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    with pytest.raises(CryptoError) as excinfo:
        get_key_provider(settings)
    assert excinfo.value.code == "kek_missing"
    assert (
        str(excinfo.value) == f"kek_missing: KEK no encontrada en {tmp_path / 'keys' / 'kek.bin'}"
    )


@SOLO_POSIX
def test_kek_con_permisos_abiertos(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.kek.chmod(0o644)
    with pytest.raises(CryptoError) as excinfo:
        get_key_provider(settings)
    assert excinfo.value.code == "kek_insecure_permissions"
    assert "permisos de la KEK inseguros" in str(excinfo.value)


def test_kek_de_tamano_incorrecto(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    rutas.kek.write_bytes(b"corta")
    with pytest.raises(CryptoError) as excinfo:
        get_key_provider(settings)
    assert excinfo.value.code == "kek_invalid"
    assert "corta" not in str(excinfo.value)


def test_proveedor_desconocido(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url, CRYPTO_PROVIDER="openbao")
    with pytest.raises(CryptoError) as excinfo:
        get_key_provider(settings)
    assert excinfo.value.code == "unknown_provider"


def test_proveedor_local_con_llaves_en_orden(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    init_keys_files(key_paths_in(tmp_path / "keys"))
    proveedor = get_key_provider(settings)
    assert isinstance(proveedor, LocalFileProvider)


async def test_el_lifespan_falla_sin_kek_y_el_log_no_lleva_material(
    tmp_path: Path, test_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path, test_database_url)
    rutas = key_paths_in(tmp_path / "keys")
    init_keys_files(rutas)
    kek = rutas.kek.read_bytes()
    rutas.kek.unlink()
    app = create_app(settings, run_migrations_on_startup=False)
    with caplog.at_level(logging.DEBUG), pytest.raises(CryptoError, match="kek_missing"):
        async with app.router.lifespan_context(app):
            pass
    assert kek.hex() not in caplog.text
    assert base64.b64encode(kek).decode() not in caplog.text
    with pytest.raises(CryptoError):
        current_provider()


async def test_el_lifespan_registra_el_proveedor(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    init_keys_files(key_paths_in(tmp_path / "keys"))
    app = create_app(settings, run_migrations_on_startup=False)
    async with app.router.lifespan_context(app):
        assert isinstance(current_provider(), LocalFileProvider)
    configure_provider(None)
    with pytest.raises(CryptoError):
        current_provider()
