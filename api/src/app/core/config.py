"""Configuración desde `.env` (US-011). Stub: se implementa en S0-B1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

NON_API_ENV_VARS: frozenset[str] = frozenset()


class ConfigError(Exception):
    """Error de configuración legible: nombra la variable, nunca su valor."""

    def __init__(self, missing: list[str], invalid: list[str]) -> None:
        raise NotImplementedError


class Settings:
    def __init__(self, **kwargs: Any) -> None:
        raise NotImplementedError


def validate_crypto_provider(provider: str, kek_path: Path | None) -> None:
    raise NotImplementedError


def load_settings(env_file: Path | str | None = ".env") -> Settings:
    raise NotImplementedError


def get_settings() -> Settings:
    raise NotImplementedError


def reset_settings_cache() -> None:
    raise NotImplementedError
