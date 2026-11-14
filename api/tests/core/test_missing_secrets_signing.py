"""`missing_secrets`: la llave de firma solo se exige a quien firma (S7-D23 (5), M-4)."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from app.core.config import Settings, missing_secrets


def _settings() -> Settings:
    return Settings.model_construct(
        DATABASE_URL=SecretStr("postgresql+asyncpg://apex:clave@db/apex"),
        JWT_PRIVATE_KEY_PATH=Path("/run/apex/keys/jwt/jwt_ed25519.pem"),
        JWT_PUBLIC_KEY_PATH=None,
        CRYPTO_PROVIDER="local",
        CRYPTO_LOCAL_KEK_PATH=Path("/run/apex/keys/custody/kek.bin"),
        CRYPTO_LOCAL_SIGNING_KEY_PATH=Path("/run/apex/keys/sign/sign-ed25519.key"),
        ENV="dev",
        UPLOADS_DIR=Path("/data"),
        CORS_ORIGINS=[],
        STORAGE_PROVIDER="local",
    )


def _sin_firma(ruta: Path) -> bool:
    return ruta.name != "sign-ed25519.key"


def test_por_omision_no_exige_la_llave_de_firma() -> None:
    assert missing_secrets(_settings(), exists=_sin_firma) == []


def test_worker_y_tools_la_exigen() -> None:
    faltan = missing_secrets(_settings(), exists=_sin_firma, signing_key=True)

    assert faltan == ["CRYPTO_LOCAL_SIGNING_KEY_PATH"]
