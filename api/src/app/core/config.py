"""Configuración del api desde `.env`, validada al arrancar (US-011).

Única puerta al entorno: fuera de este archivo nadie lee `os.environ`
(`tests/architecture/test_no_os_environ.py`). Los secretos son `SecretStr`,
ninguno tiene valor por defecto, y un error de configuración nombra la variable
sin mostrar jamás su valor.

El `.env` compartido con Compose y el CLI trae variables que no son del api
(`POSTGRES_*`, puertos, admin inicial). Para que `extra="forbid"` no rompa el
arranque, esas claves se quitan del origen dotenv antes de validar: están en
`NON_API_ENV_VARS`. Cualquier otra clave desconocida sigue fallando.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    PostgresDsn,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Variables del .env que no son del api: las lee Compose (POSTGRES_*, puertos),
# pytest en el host (TEST_DATABASE_URL) o el CLI (admin inicial, US-041).
NON_API_ENV_VARS: frozenset[str] = frozenset(
    {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TEST_DATABASE_URL",
        "ADMIN_EMAIL",
        "ADMIN_INITIAL_PASSWORD",
        "WEB_PORT",
        "API_PORT",
        "DB_PORT",
        "DB_TEST_PORT",
    }
)

_DSN = TypeAdapter(PostgresDsn)
_ESQUEMA = "postgresql+asyncpg"


class ConfigError(Exception):
    """Configuración inválida. Lleva los nombres de las variables, nunca sus valores."""

    def __init__(self, missing: list[str], invalid: list[str]) -> None:
        self.missing = sorted(set(missing))
        self.invalid = sorted(set(invalid))
        partes: list[str] = []
        if self.missing:
            partes.append("faltan: " + ", ".join(self.missing))
        if self.invalid:
            partes.append("inválidas o desconocidas: " + ", ".join(self.invalid))
        detalle = "; ".join(partes) or "sin detalle"
        super().__init__(f"Configuración inválida ({detalle}). Revisa .env y .env.example.")


def validate_crypto_provider(provider: str, kek_path: Path | None) -> None:
    """Función pura: el proveedor local exige la ruta de la KEK."""
    if provider == "local" and kek_path is None:
        raise ValueError("CRYPTO_LOCAL_KEK_PATH es obligatoria cuando CRYPTO_PROVIDER=local")


class _DotEnvSinAjenas(DotEnvSettingsSource):
    """Origen dotenv que ignora `NON_API_ENV_VARS` y rechaza cualquier otra clave desconocida."""

    def _load_env_vars(self) -> Any:
        datos = super()._load_env_vars()
        conocidas = {nombre.lower() for nombre in self.settings_cls.model_fields}
        ajenas = {nombre.lower() for nombre in NON_API_ENV_VARS}
        desconocidas = [
            clave.upper()
            for clave in datos
            if clave.lower() not in conocidas and clave.lower() not in ajenas
        ]
        if desconocidas:
            raise ConfigError(missing=[], invalid=desconocidas)
        return {clave: valor for clave, valor in datos.items() if clave.lower() not in ajenas}


class Settings(BaseSettings):
    """Variables del api. Nombres en mayúsculas, iguales a los de `.env.example`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
        validate_default=True,
    )

    # Base de datos: lleva la contraseña, por eso es secreto.
    DATABASE_URL: SecretStr

    # Llaves (volumen keys). La existencia de los archivos se comprueba al cargarlos.
    JWT_PRIVATE_KEY_PATH: Path
    JWT_PUBLIC_KEY_PATH: Path | None = None
    CRYPTO_PROVIDER: Literal["local", "openbao"]
    CRYPTO_LOCAL_KEK_PATH: Path | None = None

    # Aplicación.
    ENV: Literal["dev", "production"] = "dev"
    TZ_DISPLAY: str = "America/Bogota"  # solo para mostrar; el "hoy" lo da core/clock.py (Q28)
    UPLOADS_DIR: Path
    CORS_ORIGINS: list[str]
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    TRUSTED_PROXIES: str = ""  # IPs separadas por coma (US-036)
    COOKIE_SECURE: bool = False
    FRONT_BASE_URL: str = "http://localhost"
    APP_VERSION: str = "dev"  # SHA corto de git en la imagen (ARG GIT_SHA)

    @field_validator("DATABASE_URL")
    @classmethod
    def _dsn_asyncpg(cls, valor: SecretStr) -> SecretStr:
        try:
            dsn = _DSN.validate_python(valor.get_secret_value())
        except ValidationError:
            raise ValueError("DATABASE_URL no es un DSN de PostgreSQL válido") from None
        if dsn.scheme != _ESQUEMA:
            raise ValueError(f"DATABASE_URL debe usar el esquema {_ESQUEMA}://")
        return valor

    @field_validator("CRYPTO_LOCAL_KEK_PATH")
    @classmethod
    def _kek_si_local(cls, valor: Path | None, info: ValidationInfo) -> Path | None:
        proveedor = info.data.get("CRYPTO_PROVIDER")
        if isinstance(proveedor, str):
            validate_crypto_provider(proveedor, valor)
        return valor

    @field_validator("FRONT_BASE_URL")
    @classmethod
    def _url_http(cls, valor: str) -> str:
        if not valor.startswith(("http://", "https://")):
            raise ValueError("FRONT_BASE_URL debe empezar por http:// o https://")
        return valor.rstrip("/")

    @property
    def trusted_proxies(self) -> list[str]:
        return [ip.strip() for ip in self.TRUSTED_PROXIES.split(",") if ip.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        dotenv = _DotEnvSinAjenas(
            settings_cls,
            env_file=getattr(dotenv_settings, "env_file", None),
            env_file_encoding=settings_cls.model_config.get("env_file_encoding"),
            case_sensitive=settings_cls.model_config.get("case_sensitive"),
        )
        return (init_settings, env_settings, dotenv, file_secret_settings)


def _a_config_error(exc: ValidationError) -> ConfigError:
    """Convierte un ValidationError usando solo `loc` y `type`, nunca `input`."""
    missing: list[str] = []
    invalid: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        nombre = str(error["loc"][0]).upper() if error["loc"] else "SETTINGS"
        if error["type"] == "missing":
            missing.append(nombre)
        else:
            invalid.append(nombre)
    return ConfigError(missing=missing, invalid=invalid)


def load_settings(env_file: Path | str | None = ".env") -> Settings:
    """Carga y valida la configuración. Lanza `ConfigError` legible, sin valores."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        raise _a_config_error(exc) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings(".env")


def reset_settings_cache() -> None:
    """Solo para pruebas."""
    get_settings.cache_clear()
