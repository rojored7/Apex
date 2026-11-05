"""Pruebas de `core/config.py` (US-011, T5)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import (
    NON_API_ENV_VARS,
    ConfigError,
    Settings,
    get_settings,
    load_settings,
    missing_secrets,
    reset_settings_cache,
    validate_crypto_provider,
)

# S5-W0-3 (S5-D44): variables nuevas de OpenBao, SMTP, Telegram y exportación.
NUEVAS_S5: tuple[str, ...] = (
    "OPENBAO_ADDR",
    "OPENBAO_TOKEN_FILE",
    "OPENBAO_TIMEOUT_S",
    "CRYPTO_RECOVERY_POLL_S",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_TLS_MODE",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_API_BASE",
    "NOTIFY_MAX_ATTEMPTS",
    "NOTIFY_NET_TIMEOUT_S",
    "EXPORT_MAX_ROWS",
    "USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN",
    "USER_EXPORT_LIMIT_PER_MIN",
    "USER_EXPORT_LIMIT_PER_HOUR",
    "USER_EXPORT_LIMIT_PER_DAY",
    "BACKUP_SIGN_PUBKEY",
    "TOOLS_DB_USER",
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
    "MIGRATE_ON_STARTUP",
    "IMPORT_DIR",
    "BACKUP_DIR",
    *NUEVAS_S5,
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


def test_non_api_env_vars_contiene_las_de_operacion_y_las_diez_de_antes() -> None:
    """S4B-D79: los nombres exactos de `.env.ops.example` más los diez que ya había."""
    from pathlib import Path

    antes = {
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
    ops = Path(__file__).resolve().parents[3] / ".env.ops.example"
    claves = {
        linea.split("=", 1)[0].strip()
        for linea in ops.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.strip().startswith("#") and "=" in linea
    }
    assert claves
    # S4B-W0-3 (E7): `DATABASE_URL` pasa a `.env.ops.example` pero es un campo de `Settings`:
    # si estuviera en NON_API_ENV_VARS, el origen dotenv lo descartaria y el api no arrancaria.
    ajenas = claves - set(Settings.model_fields)
    # S5-W0-4 (S5-D150): estas dos van comentadas en `.env.ops.example`; las lee solo Compose.
    de_roles = {"MIGRATE_DB_PASSWORD", "TOOLS_DB_PASSWORD"}
    assert NON_API_ENV_VARS == antes | ajenas | de_roles
    assert "DATABASE_URL" not in NON_API_ENV_VARS


# M2 (S4B-D56): un .env mezclado con .env.ops no arranca en producción ------------------------


def test_produccion_rechaza_secretos_de_operacion_en_el_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for nombre in (
        "POSTGRES_PASSWORD",
        "APEX_API_DB_PASSWORD",
        "APEX_WORKER_DB_PASSWORD",
        "APEX_BACKUP_DB_PASSWORD",
        "RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY",
        "BACKUP_SIGN_KEY_FILE",
        "BACKUP_VERIFY_IDENTITY_FILE",
    ):
        monkeypatch.setenv(nombre, "valor-secreto-que-no-debe-salir")
        with pytest.raises(ConfigError) as excinfo:
            load_settings(env_file=escribir_env(tmp_path, ENV="production"))
        assert nombre in excinfo.value.invalid
        assert "valor-secreto-que-no-debe-salir" not in str(excinfo.value)
        monkeypatch.delenv(nombre)


def test_desarrollo_ignora_los_secretos_de_operacion_como_hoy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("APEX_API_DB_PASSWORD", "x")
    s = load_settings(env_file=escribir_env(tmp_path, ENV="dev"))
    assert s.ENV == "dev"


def test_produccion_sin_secretos_de_operacion_arranca(tmp_path: Path) -> None:
    assert load_settings(env_file=escribir_env(tmp_path, ENV="production")).ENV == "production"


def test_ops_secret_names_no_confunde_variables_publicas() -> None:
    from app.core.config import ops_secret_names

    entorno = {"BACKUP_KEEP_DAYS": "14", "APEX_WEB_IP": "172.30.0.10", "POSTGRES_USER": "apex"}
    assert ops_secret_names(entorno) == []


# S4B-W0-3 (S4B-D8): MIGRATE_ON_STARTUP ------------------------------------------------------


def test_migrate_on_startup_es_un_bool_con_valor_por_defecto_verdadero() -> None:
    campo = Settings.model_fields["MIGRATE_ON_STARTUP"]
    assert campo.annotation is bool
    assert campo.default is False, "cerrado por defecto (M3): solo desarrollo y pruebas lo activan"


@pytest.mark.parametrize(("texto", "esperado"), [("false", False), ("true", True), ("0", False)])
def test_migrate_on_startup_se_lee_del_env(tmp_path: Path, texto: str, esperado: bool) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, MIGRATE_ON_STARTUP=texto))
    assert s.MIGRATE_ON_STARTUP is esperado


def test_migrate_on_startup_sin_la_variable_vale_falso(tmp_path: Path) -> None:
    assert load_settings(env_file=escribir_env(tmp_path)).MIGRATE_ON_STARTUP is False


def test_migrate_on_startup_invalido_nombra_la_variable_sin_su_valor(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=escribir_env(tmp_path, MIGRATE_ON_STARTUP="quizas"))
    assert "MIGRATE_ON_STARTUP" in excinfo.value.invalid
    assert "quizas" not in str(excinfo.value)


def test_migrate_on_startup_no_es_una_variable_ajena() -> None:
    assert "MIGRATE_ON_STARTUP" not in NON_API_ENV_VARS


def test_el_cli_incluye_migrate_on_startup_en_los_ajustes_de_exportacion() -> None:
    from app.cli import export_settings

    assert export_settings().MIGRATE_ON_STARTUP is True


def test_las_contrasenas_de_rol_y_la_del_propietario_son_ajenas_al_api() -> None:
    """H-1: un `.env` de desarrollo que sea la suma de los dos ejemplos no tumba al api."""
    assert {
        "APEX_API_DB_PASSWORD",
        "APEX_WORKER_DB_PASSWORD",
        "APEX_BACKUP_DB_PASSWORD",
        "POSTGRES_PASSWORD",
    } <= NON_API_ENV_VARS


# S4B-B1 (S4B-D90): carpeta de importación de socios ----------------------------------------


def test_import_dir_por_defecto_es_data_imports(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path))
    assert s.IMPORT_DIR == Path("/data/imports")
    assert isinstance(s.IMPORT_DIR, Path)


def test_import_dir_se_lee_del_entorno(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, IMPORT_DIR="/srv/apex/importar"))
    assert s.IMPORT_DIR == Path("/srv/apex/importar")


def test_import_dir_no_es_una_variable_ajena_al_api() -> None:
    assert "IMPORT_DIR" in Settings.model_fields
    assert "IMPORT_DIR" not in NON_API_ENV_VARS


@pytest.mark.parametrize(
    "ruta",
    [
        "/data/uploads",
        "/data/uploads/importar",
        "/data",
        "/run/apex/keys",
        "/run/apex/keys/importar",
        "/run/apex",
        "/data/uploads/../uploads",
    ],
)
def test_import_dir_no_puede_ser_contener_ni_estar_dentro_de_datos_o_llaves(
    tmp_path: Path, ruta: str
) -> None:
    """S4B-B1 (revisión de seguridad, LOW): IMPORT_DIR aparte de UPLOADS_DIR y de la KEK."""
    with pytest.raises(ConfigError):  # error de modelo: no nombra un campo suelto
        load_settings(env_file=escribir_env(tmp_path, IMPORT_DIR=ruta))


def test_import_dir_aparte_de_los_datos_y_las_llaves_se_acepta(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, IMPORT_DIR="/data/imports"))
    assert s.IMPORT_DIR == Path("/data/imports")


# S4B-B2 (S4B-D25): volumen de respaldos que lee backup_check --------------------------------------


def test_backup_dir_por_defecto_es_data_backups(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path))
    assert s.BACKUP_DIR == Path("/data/backups")
    assert isinstance(s.BACKUP_DIR, Path)


def test_backup_dir_se_lee_del_entorno(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, BACKUP_DIR="/srv/apex/respaldos"))
    assert s.BACKUP_DIR == Path("/srv/apex/respaldos")


def test_backup_dir_es_campo_de_settings_y_no_una_variable_ajena() -> None:
    assert "BACKUP_DIR" in Settings.model_fields
    assert "BACKUP_DIR" not in NON_API_ENV_VARS


# S4B-B2 (revisión de seguridad, LOW): BACKUP_DIR aparte de los datos, las llaves y la importación


@pytest.mark.parametrize(
    "ruta",
    [
        "/data/uploads",
        "/data/uploads/respaldos",
        "/data",
        "/run/apex/keys",
        "/run/apex/keys/respaldos",
        "/run/apex",
        "/data/imports",
        "/data/imports/respaldos",
        "/data/uploads/../uploads",
    ],
)
def test_backup_dir_no_puede_ser_contener_ni_estar_dentro_de_datos_llaves_o_importacion(
    tmp_path: Path, ruta: str
) -> None:
    with pytest.raises(ConfigError):
        load_settings(env_file=escribir_env(tmp_path, BACKUP_DIR=ruta, IMPORT_DIR="/data/imports"))


def test_backup_dir_no_puede_contener_a_import_dir_aunque_este_sea_el_defecto(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigError):
        load_settings(env_file=escribir_env(tmp_path, BACKUP_DIR="/data"))


def test_backup_dir_aparte_se_acepta(tmp_path: Path) -> None:
    s = load_settings(env_file=escribir_env(tmp_path, BACKUP_DIR="/srv/apex/respaldos"))
    assert s.BACKUP_DIR == Path("/srv/apex/respaldos")


def test_el_backup_dir_por_defecto_no_se_comprueba(tmp_path: Path) -> None:
    """Como `IMPORT_DIR`: el valor por defecto vive aparte en la imagen."""
    s = load_settings(env_file=escribir_env(tmp_path, UPLOADS_DIR="/data"))
    assert s.BACKUP_DIR == Path("/data/backups")


# S5-W0-3 (S5-D17, S5-D44, S5-D81): OpenBao, SMTP, Telegram, exportación -----------------------

OPENBAO_BASE: dict[str, str | None] = {
    "CRYPTO_PROVIDER": "openbao",
    "CRYPTO_LOCAL_KEK_PATH": None,
    "OPENBAO_TOKEN_FILE": "/run/apex/openbao/token",
}
SMTP_COMPLETO: dict[str, str | None] = {
    "SMTP_HOST": "smtp.ejemplo.test",
    "SMTP_USER": "apex",
    "SMTP_PASSWORD": "clave-smtp-no-real",
    "SMTP_FROM": "apex@ejemplo.test",
}
TELEGRAM_OFICIAL = "https://api.telegram.org"
TOKEN_TELEGRAM = "123456:AAH-token-no-real-1234567890"  # noqa: S105
LLAVE_MINISIGN = base64.b64encode(b"Ed" + bytes(range(40))).decode()


def _cargar(tmp_path: Path, **cambios: str | None) -> Settings:
    return load_settings(env_file=escribir_env(tmp_path, **cambios))


def _rechaza(tmp_path: Path, nombre: str, **cambios: str | None) -> ConfigError:
    # Sin esto, `extra="forbid"` rechazaría una variable inexistente y la prueba pasaría en falso.
    assert nombre in Settings.model_fields, f"{nombre} aún no es un campo de Settings"
    with pytest.raises(ConfigError) as excinfo:
        _cargar(tmp_path, **cambios)
    assert nombre in excinfo.value.invalid or nombre in excinfo.value.missing, str(excinfo.value)
    return excinfo.value


def test_openbao_addr_por_defecto_es_http_openbao_8200(tmp_path: Path) -> None:
    s = _cargar(tmp_path)
    assert s.OPENBAO_ADDR == "http://openbao:8200"


@pytest.mark.parametrize(
    "direccion",
    ["http://openbao:8200", "http://localhost:8200", "http://127.0.0.1:8200"],
)
def test_openbao_addr_http_se_acepta_en_los_tres_hosts_locales(
    tmp_path: Path, direccion: str
) -> None:
    assert _cargar(tmp_path, OPENBAO_ADDR=direccion).OPENBAO_ADDR == direccion


@pytest.mark.parametrize(
    "direccion",
    ["http://bao.ejemplo.test:8200", "http://10.0.0.5:8200", "http://openbao.evil.test:8200"],
)
def test_openbao_addr_http_hacia_otro_host_se_rechaza(tmp_path: Path, direccion: str) -> None:
    error = _rechaza(tmp_path, "OPENBAO_ADDR", OPENBAO_ADDR=direccion)
    assert direccion not in str(error)


def test_openbao_addr_https_hacia_otro_host_se_acepta(tmp_path: Path) -> None:
    s = _cargar(tmp_path, OPENBAO_ADDR="https://bao.ejemplo.test:8200")
    assert s.OPENBAO_ADDR.startswith("https://")


@pytest.mark.parametrize("direccion", ["ftp://openbao:8200", "openbao:8200", "https://"])
def test_openbao_addr_con_esquema_o_forma_invalida_se_rechaza(
    tmp_path: Path, direccion: str
) -> None:
    _rechaza(tmp_path, "OPENBAO_ADDR", OPENBAO_ADDR=direccion)


def test_proveedor_openbao_exige_la_ruta_del_token(tmp_path: Path) -> None:
    _rechaza(tmp_path, "OPENBAO_TOKEN_FILE", **{**OPENBAO_BASE, "OPENBAO_TOKEN_FILE": None})


def test_proveedor_openbao_con_token_no_exige_kek_local(tmp_path: Path) -> None:
    s = _cargar(tmp_path, **OPENBAO_BASE)
    assert s.CRYPTO_PROVIDER == "openbao"
    assert s.OPENBAO_TOKEN_FILE == Path("/run/apex/openbao/token")
    assert s.CRYPTO_LOCAL_KEK_PATH is None


def test_proveedor_local_no_exige_el_token_de_openbao(tmp_path: Path) -> None:
    assert _cargar(tmp_path).OPENBAO_TOKEN_FILE is None


def test_missing_secrets_con_openbao_exige_el_token_y_no_la_kek(tmp_path: Path) -> None:
    settings = _cargar(tmp_path, **OPENBAO_BASE)
    sin_token = missing_secrets(settings, exists=lambda ruta: ruta.name != "token")
    assert sin_token == ["OPENBAO_TOKEN_FILE"]
    todo_ausente = missing_secrets(settings, exists=lambda _ruta: False)
    assert "OPENBAO_TOKEN_FILE" in todo_ausente
    assert "CRYPTO_LOCAL_KEK_PATH" not in todo_ausente
    assert "CRYPTO_LOCAL_SIGNING_KEY_PATH" not in todo_ausente
    assert missing_secrets(settings, exists=lambda _ruta: True) == []


def test_missing_secrets_con_local_sigue_sin_pedir_el_token_de_openbao(tmp_path: Path) -> None:
    settings = _cargar(tmp_path)
    assert "OPENBAO_TOKEN_FILE" not in missing_secrets(settings, exists=lambda _ruta: False)


def test_valores_por_defecto_de_s5(tmp_path: Path) -> None:
    s = _cargar(tmp_path)
    assert s.CRYPTO_RECOVERY_POLL_S == 20
    assert s.OPENBAO_TIMEOUT_S == 5
    assert s.NOTIFY_MAX_ATTEMPTS == 3
    assert s.NOTIFY_NET_TIMEOUT_S == 10
    assert s.EXPORT_MAX_ROWS == 20000
    assert s.SMTP_PORT == 587
    assert s.TELEGRAM_API_BASE == TELEGRAM_OFICIAL


@pytest.mark.parametrize(
    "nombre",
    ["CRYPTO_RECOVERY_POLL_S", "OPENBAO_TIMEOUT_S", "NOTIFY_MAX_ATTEMPTS", "EXPORT_MAX_ROWS"],
)
def test_los_numeros_de_s5_exigen_mayor_que_cero(tmp_path: Path, nombre: str) -> None:
    _rechaza(tmp_path, nombre, **{nombre: "0"})


def test_smtp_sin_ningun_campo_es_valido_y_deja_el_correo_apagado(tmp_path: Path) -> None:
    s = _cargar(tmp_path)
    assert s.SMTP_HOST is None and s.SMTP_PASSWORD is None and s.SMTP_FROM is None


def test_smtp_completo_se_acepta(tmp_path: Path) -> None:
    s = _cargar(tmp_path, **SMTP_COMPLETO)
    assert s.SMTP_HOST == "smtp.ejemplo.test" and s.SMTP_TLS_MODE == "starttls"


@pytest.mark.parametrize("falta", ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"])
def test_smtp_es_todo_o_nada_y_nombra_lo_que_falta(tmp_path: Path, falta: str) -> None:
    error = _rechaza(tmp_path, falta, **{**SMTP_COMPLETO, falta: None})
    assert "clave-smtp-no-real" not in str(error)


def test_smtp_tls_none_solo_con_env_dev(tmp_path: Path) -> None:
    _rechaza(tmp_path, "SMTP_TLS_MODE", **SMTP_COMPLETO, SMTP_TLS_MODE="none", ENV="production")
    s = _cargar(tmp_path, **SMTP_COMPLETO, SMTP_TLS_MODE="none", ENV="dev")
    assert s.SMTP_TLS_MODE == "none"


def test_smtp_tls_modo_desconocido_se_rechaza(tmp_path: Path) -> None:
    _rechaza(tmp_path, "SMTP_TLS_MODE", **SMTP_COMPLETO, SMTP_TLS_MODE="ssl2")


def test_telegram_api_base_distinta_de_la_oficial_solo_con_env_dev(tmp_path: Path) -> None:
    _rechaza(
        tmp_path, "TELEGRAM_API_BASE", TELEGRAM_API_BASE="http://127.0.0.1:9", ENV="production"
    )
    s = _cargar(tmp_path, TELEGRAM_API_BASE="http://127.0.0.1:9", ENV="dev")
    assert s.TELEGRAM_API_BASE == "http://127.0.0.1:9"
    oficial = _cargar(tmp_path, TELEGRAM_API_BASE=TELEGRAM_OFICIAL, ENV="production")
    assert oficial.TELEGRAM_API_BASE == TELEGRAM_OFICIAL


def test_smtp_password_y_telegram_token_son_secretstr_con_repr_enmascarado(
    tmp_path: Path,
) -> None:
    s = _cargar(tmp_path, **SMTP_COMPLETO, TELEGRAM_BOT_TOKEN=TOKEN_TELEGRAM)
    assert isinstance(s.SMTP_PASSWORD, SecretStr)
    assert isinstance(s.TELEGRAM_BOT_TOKEN, SecretStr)
    texto = repr(s) + str(s) + repr(s.SMTP_PASSWORD) + repr(s.TELEGRAM_BOT_TOKEN)
    assert "clave-smtp-no-real" not in texto
    assert "AAH-token-no-real" not in texto
    assert "**********" in repr(s.SMTP_PASSWORD)
    assert s.SMTP_PASSWORD.get_secret_value() == "clave-smtp-no-real"


def test_los_secretos_de_s5_son_opcionales_y_sin_valor_por_defecto_real() -> None:
    for nombre in ("SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN"):
        assert nombre in Settings.model_fields, nombre
        assert Settings.model_fields[nombre].default is None, nombre


def test_las_cuatro_user_de_s5_d81_tienen_su_valor_por_defecto(tmp_path: Path) -> None:
    s = _cargar(tmp_path)
    assert s.USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN == 30
    assert s.USER_EXPORT_LIMIT_PER_MIN == 2
    assert s.USER_EXPORT_LIMIT_PER_HOUR == 6
    assert s.USER_EXPORT_LIMIT_PER_DAY == 20


@pytest.mark.parametrize(
    "nombre",
    [
        "USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN",
        "USER_EXPORT_LIMIT_PER_MIN",
        "USER_EXPORT_LIMIT_PER_HOUR",
        "USER_EXPORT_LIMIT_PER_DAY",
    ],
)
def test_las_cuatro_user_de_s5_d81_exigen_mayor_que_cero(tmp_path: Path, nombre: str) -> None:
    _rechaza(tmp_path, nombre, **{nombre: "0"})
    assert getattr(_cargar(tmp_path, **{nombre: "7"}), nombre) == 7


def test_backup_sign_pubkey_es_opcional(tmp_path: Path) -> None:
    assert _cargar(tmp_path).BACKUP_SIGN_PUBKEY in (None, "")


def test_backup_sign_pubkey_con_formato_minisign_se_acepta(tmp_path: Path) -> None:
    assert LLAVE_MINISIGN.startswith("RW") and len(LLAVE_MINISIGN) == 56
    assert _cargar(tmp_path, BACKUP_SIGN_PUBKEY=LLAVE_MINISIGN).BACKUP_SIGN_PUBKEY == LLAVE_MINISIGN


@pytest.mark.parametrize(
    "valor",
    ["no-es-una-llave", "RW", "RWQ" + "A" * 10, "XX" + LLAVE_MINISIGN[2:], LLAVE_MINISIGN + "AA"],
    ids=["texto", "solo-prefijo", "corta", "prefijo-ajeno", "larga"],
)
def test_backup_sign_pubkey_con_formato_invalido_se_rechaza(tmp_path: Path, valor: str) -> None:
    _rechaza(tmp_path, "BACKUP_SIGN_PUBKEY", BACKUP_SIGN_PUBKEY=valor)


def test_produccion_acepta_backup_sign_pubkey_en_el_entorno_pero_no_la_llave_privada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`BACKUP_SIGN_PUBKEY` pasa a `Settings` (no es secreta): el prefijo `BACKUP_SIGN_` de M2
    ya no la cuenta como secreto de operación, pero `BACKUP_SIGN_KEY_FILE` sí."""
    from app.core.config import ops_secret_names

    assert ops_secret_names({"BACKUP_SIGN_PUBKEY": LLAVE_MINISIGN}) == []
    assert ops_secret_names({"BACKUP_SIGN_KEY_FILE": "/x"}) == ["BACKUP_SIGN_KEY_FILE"]
    monkeypatch.setenv("BACKUP_SIGN_PUBKEY", LLAVE_MINISIGN)
    s = _cargar(tmp_path, ENV="production")
    assert s.BACKUP_SIGN_PUBKEY == LLAVE_MINISIGN


def test_non_api_env_vars_de_s5_son_las_claves_de_operacion_que_no_son_de_settings() -> None:
    ops = Path(__file__).resolve().parents[3] / ".env.ops.example"
    claves = {
        linea.split("=", 1)[0].strip()
        for linea in ops.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.strip().startswith("#") and "=" in linea
    }
    de_settings = {"SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN", "BACKUP_SIGN_PUBKEY"}
    assert de_settings <= claves, "deben vivir en .env.ops.example (S5-D44)"
    assert de_settings <= set(Settings.model_fields), "son campos de Settings"
    assert not de_settings & NON_API_ENV_VARS, "no son ajenas: Settings las lee"
    ajenas_nuevas = {"TOOLS_DB_USER", "MIGRATE_DB_USER", "APEX_CUSTODY_SUBNET"}
    assert ajenas_nuevas <= claves
    assert ajenas_nuevas <= NON_API_ENV_VARS
    assert NON_API_ENV_VARS >= claves - set(Settings.model_fields)


def test_un_env_suma_de_los_dos_ejemplos_con_claves_s5_no_tumba_al_api(tmp_path: Path) -> None:
    s = _cargar(
        tmp_path,
        **SMTP_COMPLETO,
        TOOLS_DB_USER="apex",
        MIGRATE_DB_USER="apex",
        APEX_CUSTODY_SUBNET="172.31.0.0/24",
        TELEGRAM_BOT_TOKEN=TOKEN_TELEGRAM,
        TELEGRAM_CHAT_ID="-100123",
    )
    assert s.TELEGRAM_CHAT_ID == "-100123"
