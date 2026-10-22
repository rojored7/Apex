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

import json
from collections.abc import Callable
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit

from pydantic import (
    Field,
    PostgresDsn,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Variables del .env que no son del api: las lee Compose (POSTGRES_*, puertos),
# pytest en el host (TEST_DATABASE_URL) o el CLI (admin inicial, US-041: vive en `.env.seed`
# y solo lo lee `SeedSettings` en el servicio tools; M-8).
NON_API_ENV_VARS: frozenset[str] = frozenset(
    {
        "ADMIN_EMAIL",
        "ADMIN_INITIAL_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TEST_DATABASE_URL",
        "WEB_PORT",
        "API_PORT",
        "DB_PORT",
        "DB_TEST_PORT",
    }
)

_DSN = TypeAdapter(PostgresDsn)
# Piso de la política N-10 en producción (M5 de la revisión general). `core/security.py` lo
# expone como `PASSWORD_MIN_LENGTH` y los schemas de contraseña nueva lo usan como `min_length`.
PASSWORD_MIN_LENGTH_FLOOR: Final[int] = 12
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
    # Llave Ed25519 de firma del bus (semilla cruda de 32 bytes); la crea `init-keys`.
    CRYPTO_LOCAL_SIGNING_KEY_PATH: Path = Path("/run/apex/keys/sign-ed25519.key")

    # Aplicación.
    ENV: Literal["dev", "production"] = "production"  # falla cerrado: /docs solo con ENV=dev
    TZ_DISPLAY: str = "America/Bogota"  # solo para mostrar; el "hoy" lo da core/clock.py (Q28)
    UPLOADS_DIR: Path
    # Orígenes exactos separados por coma (o lista JSON); vacío = sin CORS; nunca `*` (US-037).
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    TRUSTED_PROXIES: str = ""  # redes CIDR o IPs separadas por coma (US-036)
    RATE_LIMIT_MAX_KEYS: int = Field(default=10000, gt=0)
    # Riesgo aceptado P7 (LAN sin TLS): con ENV=production se exige COOKIE_SECURE=true salvo que
    # esta variable lo autorice de forma explícita (M-9). Va antes de COOKIE_SECURE porque el
    # validador de esa variable la lee.
    ALLOW_INSECURE_COOKIE: bool = False
    COOKIE_SECURE: bool = False
    FRONT_BASE_URL: str = "http://localhost"
    APP_VERSION: str = "dev"  # SHA corto de git en la imagen (ARG GIT_SHA)

    # Contraseñas (US-032): argon2id con los valores por defecto de argon2-cffi; en producción
    # no se aceptan por debajo de ellos. Política N-10: longitud mínima y lista de comunes.
    ARGON2_TIME_COST: int = Field(default=3, gt=0)
    ARGON2_MEMORY_COST_KIB: int = Field(default=65536, gt=0)
    ARGON2_PARALLELISM: int = Field(default=4, gt=0)
    PASSWORD_MIN_LENGTH: int = Field(default=PASSWORD_MIN_LENGTH_FLOOR, gt=0)

    # Sesiones (US-033): access JWT EdDSA de 15 minutos con tolerancia de 30 s (N-14) y
    # refresh opaco de 7 días en cookie HttpOnly (N-13).
    ACCESS_TOKEN_TTL_S: int = Field(default=900, gt=0)
    REFRESH_TOKEN_TTL_DAYS: int = Field(default=7, gt=0)
    JWT_LEEWAY_S: int = Field(default=30, ge=0)

    # Límites de intentos (S2-B2; E5 y E9 del plan; S2-D10, H-4, L-12). Las rutas por IP usan
    # ventanas de 60 s; el límite por cuenta solo cuenta fallos y su clave es (correo, red /24 o
    # /64); el bloqueo persistente llega a los `LOGIN_LOCK_AFTER` fallos consecutivos.
    LOGIN_IP_LIMIT: int = Field(default=5, gt=0)
    LOGIN_IP_WINDOW_S: int = Field(default=60, gt=0)
    LOGIN_ACCOUNT_LIMIT: int = Field(default=10, gt=0)
    LOGIN_ACCOUNT_WINDOW_S: int = Field(default=900, gt=0)
    LOGIN_ACCOUNT_GLOBAL_LIMIT: int = Field(default=100, gt=0)
    LOGIN_ACCOUNT_GLOBAL_WINDOW_S: int = Field(default=3600, gt=0)
    LOGIN_LOCK_AFTER: int = Field(default=20, gt=0)
    REFRESH_IP_LIMIT: int = Field(default=60, gt=0)
    RESET_IP_LIMIT: int = Field(default=10, gt=0)
    FORGOT_IP_LIMIT: int = Field(default=5, gt=0)
    LOGOUT_IP_LIMIT: int = Field(default=30, gt=0)
    # Orígenes aceptados por `require_same_origin` en login, refresh y logout (M-1, S2-D38);
    # vacío = el origen de FRONT_BASE_URL.
    AUTH_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = []
    # Piso de duración de toda respuesta 401 de login y de todo forgot (M-6, S2-D39). Revisión de
    # seguridad V10 (N-7): 75 ms (1,5 veces la mediana de S2-B2) quedaba por debajo de la rama de
    # cuenta existente bajo contención del candado de auditoría; el piso es el p99, 150 ms.
    LOGIN_MIN_DURATION_MS: int = Field(default=150, gt=0)
    # Gracia del reuso de refresh (M-2) y tope absoluto de una familia de refresh (L-4).
    REFRESH_REUSE_GRACE_S: int = Field(default=10, gt=0)
    REFRESH_ABSOLUTE_TTL_DAYS: int = Field(default=30, gt=0)

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

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _origenes(cls, valor: object) -> list[str]:
        if isinstance(valor, list):
            return parse_origins(",".join(str(v) for v in valor))
        return parse_origins(str(valor) if valor is not None else "")

    @field_validator("AUTH_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _origenes_de_sesion(cls, valor: object) -> list[str]:
        if isinstance(valor, list):
            return parse_origins(",".join(str(v) for v in valor))
        return parse_origins(str(valor) if valor is not None else "")

    @field_validator("COOKIE_SECURE")
    @classmethod
    def _cookie_segura_en_produccion(cls, valor: bool, info: ValidationInfo) -> bool:
        entorno = info.data.get("ENV")
        if isinstance(entorno, str):
            validate_cookie_security(
                entorno, valor, bool(info.data.get("ALLOW_INSECURE_COOKIE", False))
            )
        return valor

    @field_validator("PASSWORD_MIN_LENGTH")
    @classmethod
    def _contrasena_minima_en_produccion(cls, valor: int, info: ValidationInfo) -> int:
        """M5 de la revisión general: en producción nunca por debajo de `PASSWORD_MIN_LENGTH`
        de `core/security.py` (12, N-10); en dev se admite menos para pruebas manuales."""
        if info.data.get("ENV") == "production" and valor < PASSWORD_MIN_LENGTH_FLOOR:
            raise ValueError(
                f"PASSWORD_MIN_LENGTH no puede ser menor que {PASSWORD_MIN_LENGTH_FLOOR} "
                "en producción"
            )
        return valor

    @field_validator("TRUSTED_PROXIES")
    @classmethod
    def _redes_de_confianza(cls, valor: str) -> str:
        for parte in valor.split(","):
            if parte.strip():
                ip_network(parte.strip(), strict=False)  # ValueError si no es red ni IP
        return valor

    @field_validator("FRONT_BASE_URL")
    @classmethod
    def _url_http(cls, valor: str) -> str:
        if not valor.startswith(("http://", "https://")):
            raise ValueError("FRONT_BASE_URL debe empezar por http:// o https://")
        return valor.rstrip("/")

    @model_validator(mode="after")
    def _argon2_no_mas_debil_que_el_defecto_en_produccion(self) -> Settings:
        if self.ENV == "production" and (
            self.ARGON2_TIME_COST < 3
            or self.ARGON2_MEMORY_COST_KIB < 65536
            or self.ARGON2_PARALLELISM < 4
        ):
            raise ValueError(
                "ARGON2_* no puede estar por debajo de los valores por defecto en producción"
            )
        return self

    @property
    def trusted_proxies(self) -> list[IPv4Network | IPv6Network]:
        """Redes de confianza para `X-Forwarded-For` (US-036); una IP suelta es una red /32."""
        return [
            ip_network(parte.strip(), strict=False)
            for parte in self.TRUSTED_PROXIES.split(",")
            if parte.strip()
        ]

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


def validate_cookie_security(env: str, cookie_secure: bool, allow_insecure: bool) -> None:
    """Función pura (M-9): en producción la cookie lleva `Secure` salvo excepción explícita."""
    if env == "production" and not cookie_secure and not allow_insecure:
        raise ValueError(
            "COOKIE_SECURE debe ser true en producción "
            "(o ALLOW_INSECURE_COOKIE=true como riesgo aceptado P7)"
        )


class SeedSettings(BaseSettings):
    """Variables del primer admin, solo para `cli seed` (servicio `tools`; M-8, S2-D12, L-9).

    Lee `.env.seed` (si no existe, solo el entorno) con `extra="forbid"`.
    """

    model_config = SettingsConfigDict(
        env_file=".env.seed",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    ADMIN_EMAIL: str | None = None
    ADMIN_INITIAL_PASSWORD: SecretStr | None = None


def load_seed_settings(env_file: Path | str | None = ".env.seed") -> SeedSettings:
    """Carga `SeedSettings` (el entorno manda sobre el archivo); `ConfigError` sin valores."""
    try:
        return SeedSettings(_env_file=env_file)
    except ValidationError as exc:
        raise _a_config_error(exc) from None


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


# US-037: orígenes CORS -----------------------------------------------------------------


def parse_origins(value: str) -> list[str]:
    """Orígenes exactos `esquema://host[:puerto]`, sin ruta ni barra final, sin duplicados.

    Acepta una lista separada por comas o una lista JSON. `*` y `null` fallan.
    """
    texto = value.strip()
    if not texto:
        return []
    partes: list[str]
    if texto.startswith("["):
        cargado = json.loads(texto)
        if not isinstance(cargado, list):
            raise ValueError("CORS_ORIGINS debe ser una lista de orígenes")
        partes = [str(p) for p in cargado]
    else:
        partes = texto.split(",")
    salida: list[str] = []
    for parte in partes:
        origen = parte.strip()
        if not origen:
            continue
        if origen in {"*", "null"}:
            raise ValueError("CORS_ORIGINS no admite '*' ni 'null'")
        url = urlsplit(origen)
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError(f"CORS_ORIGINS: origen inválido: {origen}")
        if url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError(f"CORS_ORIGINS: un origen no lleva ruta ni query: {origen}")
        normalizado = f"{url.scheme}://{url.netloc}"
        if normalizado not in salida:
            salida.append(normalizado)
    return salida


# US-039: secretos obligatorios al arrancar ------------------------------------------


def missing_secrets(settings: Settings, exists: Callable[[Path], bool] = Path.is_file) -> list[str]:
    """Nombres de variable cuyo secreto o archivo falta (nunca valores), ordenados."""
    faltan: list[str] = []
    dsn = settings.DATABASE_URL.get_secret_value()
    if "@" not in dsn or ":" not in dsn.split("@", 1)[0].split("://", 1)[-1]:
        faltan.append("DATABASE_URL")
    if not exists(settings.JWT_PRIVATE_KEY_PATH):
        faltan.append("JWT_PRIVATE_KEY_PATH")
    if settings.CRYPTO_PROVIDER == "local":
        if settings.CRYPTO_LOCAL_KEK_PATH is None or not exists(settings.CRYPTO_LOCAL_KEK_PATH):
            faltan.append("CRYPTO_LOCAL_KEK_PATH")
        if not exists(settings.CRYPTO_LOCAL_SIGNING_KEY_PATH):
            faltan.append("CRYPTO_LOCAL_SIGNING_KEY_PATH")
    return sorted(faltan)


def check_secrets_or_exit(settings: Settings) -> None:
    """Lanza `StartupError("Faltan secretos: A, B")` con solo nombres de variable."""
    from app.core.security import StartupError  # import perezoso: security importa config

    faltan = missing_secrets(settings)
    if faltan:
        raise StartupError("Faltan secretos: " + ", ".join(faltan))
