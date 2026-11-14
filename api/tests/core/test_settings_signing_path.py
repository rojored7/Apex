"""Validador de `Settings` de la ruta de la llave de firma (S7-D23 (1), hallazgo 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ConfigError, Settings, load_settings
from tests.core.test_config import _cargar, escribir_env

KEK = "/run/apex/keys/custody/kek.bin"
JWT = "/run/apex/keys/jwt/jwt_ed25519.pem"


def test_ruta_por_omision_en_sign() -> None:
    por_defecto = Settings.model_fields["CRYPTO_LOCAL_SIGNING_KEY_PATH"].default

    assert Path(por_defecto) == Path("/run/apex/keys/sign/sign-ed25519.key")


def test_ruta_de_firma_bajo_la_carpeta_de_la_kek_falla_nombrando_la_variable(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigError) as excinfo:
        _cargar(
            tmp_path,
            CRYPTO_LOCAL_KEK_PATH=KEK,
            JWT_PRIVATE_KEY_PATH=JWT,
            CRYPTO_LOCAL_SIGNING_KEY_PATH="/run/apex/keys/custody/sign-ed25519.key",
        )

    assert "CRYPTO_LOCAL_SIGNING_KEY_PATH" in excinfo.value.invalid


def test_ruta_de_firma_bajo_jwt_falla(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        _cargar(
            tmp_path,
            CRYPTO_LOCAL_KEK_PATH=KEK,
            JWT_PRIVATE_KEY_PATH=JWT,
            CRYPTO_LOCAL_SIGNING_KEY_PATH="/run/apex/keys/jwt/sign-ed25519.key",
        )

    assert "CRYPTO_LOCAL_SIGNING_KEY_PATH" in excinfo.value.invalid


def test_firma_con_linea_vacia_aborta(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        _cargar(
            tmp_path,
            CRYPTO_LOCAL_KEK_PATH=KEK,
            JWT_PRIVATE_KEY_PATH=JWT,
            CRYPTO_LOCAL_SIGNING_KEY_PATH="",
        )

    assert "CRYPTO_LOCAL_SIGNING_KEY_PATH" in excinfo.value.invalid


def test_kek_none_con_openbao_no_rompe_el_validador(tmp_path: Path) -> None:
    ajustes = _cargar(
        tmp_path,
        CRYPTO_PROVIDER="openbao",
        CRYPTO_LOCAL_KEK_PATH=None,
        JWT_PRIVATE_KEY_PATH=JWT,
        OPENBAO_TOKEN_FILE="/run/apex/openbao/token",  # noqa: S106
    )

    assert ajustes.CRYPTO_LOCAL_KEK_PATH is None
    assert ajustes.CRYPTO_LOCAL_SIGNING_KEY_PATH == Path("/run/apex/keys/sign/sign-ed25519.key")


def test_firma_en_sign_es_valida(tmp_path: Path) -> None:
    ajustes = load_settings(
        env_file=escribir_env(
            tmp_path,
            CRYPTO_LOCAL_KEK_PATH=KEK,
            JWT_PRIVATE_KEY_PATH=JWT,
            CRYPTO_LOCAL_SIGNING_KEY_PATH="/run/apex/keys/sign/sign-ed25519.key",
        )
    )

    assert ajustes.CRYPTO_LOCAL_SIGNING_KEY_PATH.parent.name == "sign"
