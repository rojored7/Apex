"""El error de configuración nunca muestra el valor de un secreto (US-011, T6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ConfigError, load_settings, reset_settings_cache


def test_dsn_invalido_no_filtra_la_contrasena(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_settings_cache()
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:super-secreto-123@db:puerto-malo/apex\n"
        "JWT_PRIVATE_KEY_PATH=/run/apex/keys/jwt_ed25519.pem\n"
        "CRYPTO_PROVIDER=local\n"
        "CRYPTO_LOCAL_KEK_PATH=/run/apex/keys/kek.bin\n"
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
