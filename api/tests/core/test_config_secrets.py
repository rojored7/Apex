"""Secretos: `missing_secrets`, `SecretStr` en `repr` y `dump`, arranque sin fugas (US-039)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.cli import init_keys_files, key_paths_in
from app.core.config import Settings, check_secrets_or_exit, missing_secrets
from app.core.security import StartupError
from app.main import create_app

CLAVE_DB = "super-secreta-db-2026"


def _settings(tmp_path: Path, test_database_url: str, *, provider: str = "local") -> Settings:
    rutas = key_paths_in(tmp_path / "keys")
    url = test_database_url.replace("apex-test", CLAVE_DB)
    return Settings.model_construct(
        DATABASE_URL=SecretStr(url),
        JWT_PRIVATE_KEY_PATH=rutas.jwt_private,
        JWT_PUBLIC_KEY_PATH=None,
        CRYPTO_PROVIDER=provider,
        CRYPTO_LOCAL_KEK_PATH=rutas.kek,
        CRYPTO_LOCAL_SIGNING_KEY_PATH=rutas.signing_key,
        ENV="dev",
        UPLOADS_DIR=Path("/data"),
        CORS_ORIGINS=[],
    )


def test_missing_secrets(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    assert missing_secrets(settings) == sorted(
        ["CRYPTO_LOCAL_KEK_PATH", "CRYPTO_LOCAL_SIGNING_KEY_PATH", "JWT_PRIVATE_KEY_PATH"]
    )
    init_keys_files(key_paths_in(tmp_path / "keys"))
    assert missing_secrets(settings) == []
    key_paths_in(tmp_path / "keys").jwt_private.unlink()
    assert missing_secrets(settings) == ["JWT_PRIVATE_KEY_PATH"]
    assert missing_secrets(settings, exists=lambda p: True) == []
    sin_clave = Settings.model_construct(
        **{**settings.__dict__, "DATABASE_URL": SecretStr("postgresql+asyncpg://apex@db/apex")}
    )
    assert "DATABASE_URL" in missing_secrets(sin_clave, exists=lambda p: True)


def test_openbao_no_pide_la_kek(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url, provider="openbao")
    faltan = missing_secrets(settings, exists=lambda p: False)
    assert "CRYPTO_LOCAL_KEK_PATH" not in faltan and "JWT_PRIVATE_KEY_PATH" in faltan


def test_repr_y_dump_ocultan_los_secretos(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    texto = repr(settings) + settings.model_dump_json() + str(settings.model_dump())
    assert CLAVE_DB not in texto
    assert "**********" in texto


def test_check_secrets_or_exit_nombra_sin_valores(tmp_path: Path, test_database_url: str) -> None:
    settings = _settings(tmp_path, test_database_url)
    with pytest.raises(StartupError) as excinfo:
        check_secrets_or_exit(settings)
    mensaje = str(excinfo.value)
    assert mensaje.startswith("Faltan secretos: ")
    assert "CRYPTO_LOCAL_KEK_PATH, CRYPTO_LOCAL_SIGNING_KEY_PATH, JWT_PRIVATE_KEY_PATH" in mensaje
    assert CLAVE_DB not in mensaje and str(tmp_path) not in mensaje


def test_los_campos_con_sufijo_sensible_son_secretstr() -> None:
    from typing import get_args

    for nombre, campo in Settings.model_fields.items():
        if nombre.endswith(("_PASSWORD", "_TOKEN", "_SECRET")) or nombre == "DATABASE_URL":
            anotacion = campo.annotation
            assert anotacion is SecretStr or SecretStr in get_args(anotacion), nombre


async def test_el_arranque_no_deja_secretos_en_el_log(
    settings_prueba: Settings, claves_prueba: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rutas = key_paths_in(claves_prueba)
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    with caplog.at_level(logging.DEBUG):
        async with app.router.lifespan_context(app):
            pass
    texto = caplog.text
    assert settings_prueba.DATABASE_URL.get_secret_value().split("@")[0].split(":")[-1] not in texto
    assert rutas.kek.read_bytes().hex() not in texto
    assert rutas.jwt_private.read_text(encoding="ascii").splitlines()[1] not in texto
    assert ("BEGIN " + "PRIVATE KEY") not in texto


async def test_el_lifespan_falla_sin_secretos(
    tmp_path: Path, settings_prueba: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    rotas = Settings.model_construct(
        **{**settings_prueba.__dict__, "JWT_PRIVATE_KEY_PATH": tmp_path / "no.pem"}
    )
    app = create_app(rotas, run_migrations_on_startup=False)
    with caplog.at_level(logging.ERROR), pytest.raises(StartupError, match="JWT_PRIVATE_KEY_PATH"):
        async with app.router.lifespan_context(app):
            pass
