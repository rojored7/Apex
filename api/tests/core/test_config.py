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
    # M-9 (E3): sin ENV es producción, y producción exige la cookie Secure.
    "COOKIE_SECURE": "true",
}
TODAS = (
    *BASE,
    "JWT_PUBLIC_KEY_PATH",
    "ENV",
    "TZ_DISPLAY",
    "LOG_LEVEL",
    "TRUSTED_PROXIES",
    "FRONT_BASE_URL",
    "FOO",
    "ALLOW_INSECURE_COOKIE",
    "AUTH_ALLOWED_ORIGINS",
    "LOGIN_MIN_DURATION_MS",
    "LOGIN_IP_LIMIT",
    "LOGIN_IP_WINDOW_S",
    "LOGIN_ACCOUNT_LIMIT",
    "LOGIN_ACCOUNT_WINDOW_S",
    "LOGIN_ACCOUNT_GLOBAL_LIMIT",
    "LOGIN_ACCOUNT_GLOBAL_WINDOW_S",
    "LOGIN_LOCK_AFTER",
    "REFRESH_IP_LIMIT",
    "RESET_IP_LIMIT",
    "FORGOT_IP_LIMIT",
    "LOGOUT_IP_LIMIT",
    "REFRESH_REUSE_GRACE_S",
    "REFRESH_ABSOLUTE_TTL_DAYS",
    "ADMIN_EMAIL",
    "ADMIN_INITIAL_PASSWORD",
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


# S2-B2 · variables nuevas, M-9, M-8 y SeedSettings ---------------------------------------

NUEVAS_ENTERAS: dict[str, int] = {
    "LOGIN_IP_LIMIT": 5,
    "LOGIN_IP_WINDOW_S": 60,
    "LOGIN_ACCOUNT_LIMIT": 10,
    "LOGIN_ACCOUNT_WINDOW_S": 900,
    "LOGIN_ACCOUNT_GLOBAL_LIMIT": 100,
    "LOGIN_ACCOUNT_GLOBAL_WINDOW_S": 3600,
    "LOGIN_LOCK_AFTER": 20,
    "REFRESH_IP_LIMIT": 60,
    "RESET_IP_LIMIT": 10,
    "FORGOT_IP_LIMIT": 5,
    "LOGOUT_IP_LIMIT": 30,
    "REFRESH_REUSE_GRACE_S": 10,
    "REFRESH_ABSOLUTE_TTL_DAYS": 30,
}


def test_las_variables_nuevas_tienen_los_valores_de_produccion(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path))
    for nombre, valor in NUEVAS_ENTERAS.items():
        assert getattr(s, nombre) == valor, nombre
    assert s.LOGIN_MIN_DURATION_MS > 0  # el valor medido lo fija el Verde de B2 (S2-D39)
    assert s.AUTH_ALLOWED_ORIGINS == []
    assert s.ALLOW_INSECURE_COOKIE is False


@pytest.mark.parametrize("nombre", [*NUEVAS_ENTERAS, "LOGIN_MIN_DURATION_MS"])
def test_las_variables_nuevas_exigen_mayor_que_cero(tmp_path: Path, nombre: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, **{nombre: "0"}))
    assert nombre in excinfo.value.invalid


def test_auth_allowed_origins_acepta_lista_y_rechaza_comodin(tmp_path: Path) -> None:
    s = load_settings(
        env_file=escribir_env(
            tmp_path, AUTH_ALLOWED_ORIGINS="http://localhost:8180, http://localhost:5173/"
        )
    )
    assert s.AUTH_ALLOWED_ORIGINS == ["http://localhost:8180", "http://localhost:5173"]
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, AUTH_ALLOWED_ORIGINS="*"))
    assert "AUTH_ALLOWED_ORIGINS" in excinfo.value.invalid


def test_produccion_con_cookie_sin_secure_falla_y_nombra_la_variable(tmp_path: Path) -> None:
    """M-9 (S2-D13 reemplazada): en producción la cookie lleva `Secure`."""
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, COOKIE_SECURE="false"))
    assert "COOKIE_SECURE" in str(excinfo.value)
    with pytest.raises(ConfigError):
        load_settings(env_file=escribir_env(tmp_path, COOKIE_SECURE=None))  # por defecto false


def test_produccion_sin_secure_solo_con_la_excepcion_explicita(tmp_path: Path) -> None:
    """Riesgo aceptado P7 (LAN sin TLS): `ALLOW_INSECURE_COOKIE=true` lo autoriza."""
    s = load_settings(
        env_file=escribir_env(tmp_path, COOKIE_SECURE="false", ALLOW_INSECURE_COOKIE="true")
    )
    assert s.is_production and s.COOKIE_SECURE is False and s.ALLOW_INSECURE_COOKIE is True
    assert load_settings(env_file=escribir_env(tmp_path)).COOKIE_SECURE is True


def test_en_dev_la_cookie_sin_secure_se_acepta(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, ENV="dev", COOKIE_SECURE="false"))
    assert s.ENV == "dev" and s.COOKIE_SECURE is False


@pytest.mark.parametrize(
    ("env", "segura", "excepcion", "falla"),
    [
        ("production", False, False, True),
        ("production", True, False, False),
        ("production", False, True, False),
        ("production", True, True, False),
        ("dev", False, False, False),
        ("dev", True, False, False),
    ],
)
def test_validate_cookie_security_es_pura(
    env: str, segura: bool, excepcion: bool, falla: bool
) -> None:
    from app.core.config import validate_cookie_security

    if falla:
        with pytest.raises(ValueError, match="COOKIE_SECURE"):
            validate_cookie_security(env, segura, excepcion)
    else:
        validate_cookie_security(env, segura, excepcion)


def test_admin_sale_de_settings_y_entra_en_non_api_env_vars(tmp_path: Path) -> None:
    """M-8 (S2-D12): `ADMIN_*` solo las lee `SeedSettings` en el servicio `tools`."""
    assert {"ADMIN_EMAIL", "ADMIN_INITIAL_PASSWORD"} <= NON_API_ENV_VARS
    assert "ADMIN_EMAIL" not in Settings.model_fields
    assert "ADMIN_INITIAL_PASSWORD" not in Settings.model_fields
    s = load_settings(
        env_file=escribir_env(
            tmp_path,
            ADMIN_EMAIL="admin@apex.local",
            ADMIN_INITIAL_PASSWORD="x",  # noqa: S106
        )
    )
    assert not hasattr(s, "ADMIN_EMAIL")


def test_seed_settings_lee_env_seed_y_el_entorno_manda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import SeedSettings, load_seed_settings

    archivo = tmp_path / ".env.seed"
    archivo.write_text(
        "ADMIN_EMAIL=dueno@apex.co\nADMIN_INITIAL_PASSWORD=Zanahoria-Lunar-42x\n", encoding="utf-8"
    )
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    semilla = load_seed_settings(archivo)
    assert isinstance(semilla, SeedSettings)
    assert semilla.ADMIN_EMAIL == "dueno@apex.co"
    assert semilla.ADMIN_INITIAL_PASSWORD is not None
    assert semilla.ADMIN_INITIAL_PASSWORD.get_secret_value() == "Zanahoria-Lunar-42x"
    assert "Zanahoria" not in repr(semilla)
    monkeypatch.setenv("ADMIN_EMAIL", "otra@apex.co")
    assert load_seed_settings(archivo).ADMIN_EMAIL == "otra@apex.co"


def test_seed_settings_sin_archivo_lee_solo_el_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import load_seed_settings

    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    vacio = load_seed_settings(tmp_path / "no-existe.env.seed")
    assert vacio.ADMIN_EMAIL is None and vacio.ADMIN_INITIAL_PASSWORD is None


def test_seed_settings_rechaza_claves_ajenas_sin_mostrar_valores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import load_seed_settings

    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    archivo = tmp_path / ".env.seed"
    archivo.write_text("ADMIN_EMAIL=a@apex.co\nDATABASE_URL=valor-secreto-99\n", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_seed_settings(archivo)
    assert "DATABASE_URL" in excinfo.value.invalid
    assert "valor-secreto-99" not in str(excinfo.value)


# Revisión del Sprint 2: N-7 (piso de login al p99) y M5 de la general (contraseña mínima) ----


def test_el_piso_de_login_por_defecto_es_150_ms(tmp_path: Path) -> None:
    """N-7 (revisión V10): 75 ms era 1,5 veces la mediana; bajo contención del candado de
    auditoría la rama de cuenta existente lo superaba. El piso por defecto es el p99, 150 ms."""
    assert load_settings(env_file=escribir_env(tmp_path)).LOGIN_MIN_DURATION_MS == 150


@pytest.mark.parametrize("minimo", ["1", "8", "11"])
def test_en_produccion_la_contrasena_minima_no_baja_de_12(tmp_path: Path, minimo: str) -> None:
    """M5 de la revisión general: `PASSWORD_MIN_LENGTH=1` en el `.env` rompía N-10."""
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, **{"PASSWORD_MIN_LENGTH": minimo}))
    assert "PASSWORD_MIN_LENGTH" in str(excinfo.value)


def test_en_dev_la_contrasena_minima_puede_bajar_y_en_produccion_subir(tmp_path: Path) -> None:
    from app.core.security import PASSWORD_MIN_LENGTH

    assert PASSWORD_MIN_LENGTH == 12
    dev = load_settings(env_file=escribir_env(tmp_path, ENV="dev", **{"PASSWORD_MIN_LENGTH": "4"}))
    assert dev.PASSWORD_MIN_LENGTH == 4
    prod = load_settings(env_file=escribir_env(tmp_path, **{"PASSWORD_MIN_LENGTH": "16"}))
    assert prod.PASSWORD_MIN_LENGTH == 16


# S3-W0-2 · tiempos de espera de la base (S3-D43) y topes por usuario (S3-D76, E10) ---------

DB_TIMEOUTS: dict[str, int] = {
    "DB_LOCK_TIMEOUT_MS": 10000,
    "DB_STATEMENT_TIMEOUT_MS": 30000,
    "DB_IDLE_IN_TX_TIMEOUT_MS": 60000,
}
USER_TOPES: dict[str, int] = {
    "USER_WRITE_LIMIT_PER_MIN": 30,
    "USER_ADMIN_WRITE_LIMIT_PER_MIN": 30,
    "USER_MEMBERS_WRITE_LIMIT_PER_MIN": 60,
    "USER_SEARCH_LIMIT_PER_MIN": 60,
    "USER_DETAIL_LIMIT_PER_MIN": 120,
    "USER_REVEAL_LIMIT_PER_MIN": 30,
    "USER_REVEAL_LIMIT_PER_HOUR": 200,
    "USER_REVEAL_LIMIT_PER_DAY": 600,
    # S4A-B3 (S4A-D45, S4A-D47, S4A-D65): `staff-read`, `audit-verify` y `audit-verify-hour`.
    "USER_READ_LIMIT_PER_MIN": 120,
    "USER_AUDIT_VERIFY_LIMIT_PER_MIN": 3,
    "USER_AUDIT_VERIFY_LIMIT_PER_HOUR": 20,
}


def test_tiempos_de_espera_y_topes_por_usuario_con_sus_valores_por_defecto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for nombre in (*DB_TIMEOUTS, *USER_TOPES):
        monkeypatch.delenv(nombre, raising=False)
    s = load_settings(env_file=escribir_env(tmp_path))
    for nombre, valor in {**DB_TIMEOUTS, **USER_TOPES}.items():
        assert getattr(s, nombre) == valor, nombre


@pytest.mark.parametrize("nombre", list(DB_TIMEOUTS))
def test_los_tiempos_de_espera_aceptan_cero_fuera_de_produccion_y_rechazan_negativos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    """S3-D79 (decisión del orquestador en S3-B1, posterior a W0-2): el `0` sigue aceptado fuera
    de producción. Antes esta prueba aceptaba `0` con el `Settings` de producción (W0-2 fijó
    `ge=0` sin piso); no era un error de la prueba sino una decisión que cambió."""
    monkeypatch.delenv(nombre, raising=False)
    dev = load_settings(env_file=escribir_env(tmp_path, ENV="dev", **{nombre: "0"}))
    assert getattr(dev, nombre) == 0
    for env in ("dev", "production"):
        with pytest.raises(ConfigError) as excinfo:
            load_settings(env_file=escribir_env(tmp_path, ENV=env, **{nombre: "-1"}))
        assert nombre in excinfo.value.invalid


@pytest.mark.parametrize("nombre", list(DB_TIMEOUTS))
@pytest.mark.parametrize("valor", ["0", "1", "999"])
def test_en_produccion_los_tiempos_de_espera_no_bajan_de_1000_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str, valor: str
) -> None:
    """S3-D79: con `ENV=production` cada `DB_*_TIMEOUT_MS` tiene piso de 1.000 ms (como
    `PASSWORD_MIN_LENGTH`): un `.env` con `0` desactivaría la defensa de H-3 en todo el api."""
    monkeypatch.delenv(nombre, raising=False)
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, **{nombre: valor}))
    assert nombre in excinfo.value.invalid
    assert nombre in str(excinfo.value)


@pytest.mark.parametrize("nombre", list(DB_TIMEOUTS))
def test_en_produccion_1000_ms_es_el_piso_aceptado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    monkeypatch.delenv(nombre, raising=False)
    prod = load_settings(env_file=escribir_env(tmp_path, **{nombre: "1000"}))
    assert prod.ENV == "production"
    assert getattr(prod, nombre) == 1000


def test_el_cli_desactiva_los_tiempos_despues_de_validar_produccion(tmp_path: Path) -> None:
    """S3-D79: `--db-timeouts off` sigue funcionando en producción porque `cli_runtime` copia el
    `Settings` ya validado con `model_copy` (sin revalidar), no lo carga con ceros."""
    prod = load_settings(env_file=escribir_env(tmp_path))
    apagado = prod.model_copy(update=dict.fromkeys(DB_TIMEOUTS, 0))
    assert {n: getattr(apagado, n) for n in DB_TIMEOUTS} == dict.fromkeys(DB_TIMEOUTS, 0)
    assert {n: getattr(prod, n) for n in DB_TIMEOUTS} == DB_TIMEOUTS


@pytest.mark.parametrize("nombre", list(DB_TIMEOUTS))
def test_los_tiempos_de_espera_tienen_el_techo_de_postgresql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    """Revisión de seguridad de W0-2 (LOW): más de INT_MAX ms haría fallar cada conexión."""
    monkeypatch.delenv(nombre, raising=False)
    tope = load_settings(env_file=escribir_env(tmp_path, **{nombre: "2147483647"}))
    assert getattr(tope, nombre) == 2_147_483_647
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, **{nombre: "2147483648"}))
    assert nombre in excinfo.value.invalid


@pytest.mark.parametrize("nombre", list(USER_TOPES))
def test_los_topes_por_usuario_exigen_mayor_que_cero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    monkeypatch.delenv(nombre, raising=False)
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, **{nombre: "0"}))
    assert nombre in excinfo.value.invalid
    assert getattr(load_settings(env_file=escribir_env(tmp_path, **{nombre: "7"})), nombre) == 7
