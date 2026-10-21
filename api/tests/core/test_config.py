"""Pruebas de `core/config.py` (US-011, T5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import (
    NON_API_ENV_VARS,
    ConfigError,
    Settings,
    get_settings,
    load_settings,
    reset_settings_cache,
    validate_crypto_provider,
)

BASE: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://apex:clave-secreta@db:5432/apex",
    "JWT_PRIVATE_KEY_PATH": "/run/apex/keys/jwt_ed25519.pem",
    "CRYPTO_PROVIDER": "local",
    "CRYPTO_LOCAL_KEK_PATH": "/run/apex/keys/kek.bin",
    "UPLOADS_DIR": "/data/uploads",
    "CORS_ORIGINS": '["http://localhost"]',
}
TODAS = (
    *BASE,
    "JWT_PUBLIC_KEY_PATH",
    "ENV",
    "TZ_DISPLAY",
    "LOG_LEVEL",
    "TRUSTED_PROXIES",
    "COOKIE_SECURE",
    "FRONT_BASE_URL",
    "FOO",
)


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    for clave in (*TODAS, *NON_API_ENV_VARS):
        monkeypatch.delenv(clave, raising=False)
    reset_settings_cache()


def escribir_env(tmp_path: Path, **cambios: str | None) -> Path:
    valores: dict[str, str | None] = {**BASE, **cambios}
    lineas = [f"{k}={v}" for k, v in valores.items() if v is not None]
    ruta = tmp_path / ".env"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def test_env_completo_da_campos_tipados(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path))
    assert s.CRYPTO_PROVIDER == "local"
    assert isinstance(s.UPLOADS_DIR, Path)
    assert isinstance(s.CRYPTO_LOCAL_KEK_PATH, Path)
    assert s.CORS_ORIGINS == ["http://localhost"]
    assert s.LOG_LEVEL == "INFO"
    assert s.ENV == "production", "falla cerrado: sin ENV, producción"
    assert s.TZ_DISPLAY == "America/Bogota"
    assert isinstance(s.DATABASE_URL, SecretStr)


def test_falta_database_url_nombra_la_variable(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, DATABASE_URL=None))
    assert "DATABASE_URL" in excinfo.value.missing
    assert "DATABASE_URL" in str(excinfo.value)


def test_proveedor_local_sin_kek_falla(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, CRYPTO_LOCAL_KEK_PATH=None))
    assert "CRYPTO_LOCAL_KEK_PATH" in str(excinfo.value)


def test_proveedor_desconocido_falla(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, CRYPTO_PROVIDER="aws"))
    assert "CRYPTO_PROVIDER" in excinfo.value.invalid
    assert "aws" not in str(excinfo.value)


def test_dsn_con_otro_esquema_falla(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, DATABASE_URL="postgresql://apex:x@db/apex"))
    assert "DATABASE_URL" in excinfo.value.invalid


def test_repr_y_str_no_muestran_la_contrasena(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path))
    assert "clave-secreta" not in repr(s)
    assert "clave-secreta" not in str(s)
    assert "clave-secreta" in s.DATABASE_URL.get_secret_value()


def test_secretos_y_database_url_sin_valor_por_defecto() -> None:
    for nombre, campo in Settings.model_fields.items():
        if nombre == "DATABASE_URL" or campo.annotation is SecretStr:
            assert campo.is_required(), f"{nombre} no debe tener valor por defecto"


def test_variables_ajenas_se_aceptan_y_desconocidas_fallan(tmp_path: Path) -> None:
    s = load_settings(
        env_file=escribir_env(tmp_path, POSTGRES_PASSWORD="x", WEB_PORT="8180")  # noqa: S106
    )
    assert s.CRYPTO_PROVIDER == "local"
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, FOO="1"))
    assert "FOO" in excinfo.value.invalid


def test_non_api_env_vars_cubre_compose_cli_y_puertos() -> None:
    esperadas = {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "ADMIN_EMAIL",
        "ADMIN_INITIAL_PASSWORD",
        "TEST_DATABASE_URL",
        "WEB_PORT",
        "API_PORT",
        "DB_PORT",
        "DB_TEST_PORT",
    }
    assert esperadas <= NON_API_ENV_VARS


def test_validate_crypto_provider_es_pura() -> None:
    with pytest.raises(ValueError, match="CRYPTO_LOCAL_KEK_PATH"):
        validate_crypto_provider("local", None)
    validate_crypto_provider("local", Path("/run/apex/keys/kek.bin"))
    validate_crypto_provider("openbao", None)


def test_get_settings_cachea(monkeypatch: pytest.MonkeyPatch) -> None:
    for clave, valor in BASE.items():
        monkeypatch.setenv(clave, valor)
    primero = get_settings()
    assert primero is get_settings()
    reset_settings_cache()
    assert primero is not get_settings()


def test_env_dev_solo_si_se_pide(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, ENV="dev"))
    assert s.ENV == "dev"
    assert not s.is_production
    assert load_settings(env_file=escribir_env(tmp_path)).is_production
