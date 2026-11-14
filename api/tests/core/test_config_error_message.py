"""El error de configuración nunca muestra el valor de un secreto (US-011, T6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ConfigError, load_settings, reset_settings_cache


def test_dsn_invalido_no_filtra_la_contrasena(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:super-secreto-123@db:puerto-malo/apex\n"
        "JWT_PRIVATE_KEY_PATH=/run/apex/keys/jwt/jwt_ed25519.pem\n"
        "CRYPTO_PROVIDER=local\n"
        "CRYPTO_LOCAL_KEK_PATH=/run/apex/keys/custody/kek.bin\n"
        "UPLOADS_DIR=/data/uploads\n"
        'CORS_ORIGINS=["http://localhost"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=env)

    texto = str(excinfo.value) + repr(excinfo.value)
    assert "DATABASE_URL" in texto
    assert "super-secreto-123" not in texto
    assert excinfo.value.__cause__ is None, "no se encadena el ValidationError (trae input_value)"


# S6-E1 (US-153): el mensaje de `validate_origins` nombra la variable y nunca su valor ----------


def _env_con_dominio(tmp_path: Path, **cambios: str) -> Path:
    valores = {
        "DATABASE_URL": "postgresql+asyncpg://apex:clave-secreta@db:5432/apex",
        "JWT_PRIVATE_KEY_PATH": "/run/apex/keys/jwt/jwt_ed25519.pem",
        "CRYPTO_PROVIDER": "local",
        "CRYPTO_LOCAL_KEK_PATH": "/run/apex/keys/custody/kek.bin",
        "UPLOADS_DIR": "/data/uploads",
        "APEX_DOMAIN": "apex.example.com",
        "FRONT_BASE_URL": "https://apex.example.com",
        "COOKIE_SECURE": "true",
        **cambios,
    }
    env = tmp_path / ".env"
    env.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
    return env


@pytest.mark.parametrize(
    ("variable", "cambios"),
    [
        ("CORS_ORIGINS", {"CORS_ORIGINS": '["http://otro.example.com"]'}),
        ("FRONT_BASE_URL", {"FRONT_BASE_URL": "http://frente-ajeno.example.org"}),
        ("COOKIE_SECURE", {"COOKIE_SECURE": "false", "ENV": "dev"}),
        ("ALLOW_INSECURE_COOKIE", {"ALLOW_INSECURE_COOKIE": "true"}),
    ],
)
def test_el_error_de_origenes_nombra_la_variable_y_no_su_valor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str, cambios: dict[str, str]
) -> None:
    for clave in ("APEX_DOMAIN", "FRONT_BASE_URL", "COOKIE_SECURE", "CORS_ORIGINS", "ENV"):
        monkeypatch.delenv(clave, raising=False)
    reset_settings_cache()

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=_env_con_dominio(tmp_path, **cambios))

    texto = str(excinfo.value) + repr(excinfo.value)
    assert variable in excinfo.value.invalid
    assert variable in texto
    assert "otro.example.com" not in texto and "frente-ajeno" not in texto
    assert "clave-secreta" not in texto
    assert excinfo.value.__cause__ is None
