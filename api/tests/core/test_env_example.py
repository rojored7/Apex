"""`.env.example` documenta toda variable de `Settings` y no trae secretos.

US-007 (T1 y T2) y US-011 (T8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import NON_API_ENV_VARS, Settings

RAIZ = Path(__file__).resolve().parents[3]
EJEMPLO = RAIZ / ".env.example"
EJEMPLO_OPS = RAIZ / ".env.ops.example"


def _claves(ruta: Path = EJEMPLO) -> dict[str, str]:
    claves: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        claves[clave.strip()] = valor.strip()
    return claves


def test_el_ejemplo_existe() -> None:
    assert EJEMPLO.is_file()


def test_toda_variable_de_settings_esta_documentada() -> None:
    claves = {**_claves(), **_claves(EJEMPLO_OPS)}  # S4B-D79: DATABASE_URL vive en el de operacion
    faltan = [nombre for nombre in Settings.model_fields if nombre not in claves]
    assert faltan == [], f"faltan en .env.example y .env.ops.example: {faltan}"


def test_toda_clave_ajena_al_api_esta_en_non_api_env_vars() -> None:
    claves = {**_claves(), **_claves(EJEMPLO_OPS)}
    desconocidas = [
        c for c in claves if c not in Settings.model_fields and c not in NON_API_ENV_VARS
    ]
    assert desconocidas == [], f"extra='forbid' rompería el arranque con: {desconocidas}"


def test_sin_secretos_reales() -> None:
    claves = _claves()
    for clave, valor in claves.items():
        if clave.endswith(("PASSWORD", "SECRET", "TOKEN", "KEY")):
            assert valor == "" or "cambiar-esto" in valor, f"{clave} parece llevar un valor real"
    # Concatenado para que detect-private-key no marque la propia prueba.
    assert ("BEGIN " + "PRIVATE KEY") not in EJEMPLO.read_text(encoding="utf-8")
    assert "cambiar-esto" in _claves(EJEMPLO_OPS)["DATABASE_URL"]


def test_ningun_valor_de_ejemplo_parece_real() -> None:
    """US-039 T4: sin PEM y sin valores largos en base64 (32 bytes o más)."""
    import re

    for clave, valor in _claves().items():
        assert not re.fullmatch(r"[A-Za-z0-9+/=_-]{43,}", valor), f"{clave} parece un secreto real"
    texto = EJEMPLO.read_text(encoding="utf-8")
    assert "-----BEGIN" not in texto


def test_cors_vacio_y_proxies_documentados() -> None:
    claves = _claves()
    assert claves["CORS_ORIGINS"] == "" and "*" not in claves["CORS_ORIGINS"]
    assert "TRUSTED_PROXIES" in claves and "RATE_LIMIT_MAX_KEYS" in claves


# S2-B2 · M-8 (sin ADMIN_*), E3 y E9 (variables nuevas como líneas activas) --------------

NUEVAS_ACTIVAS: dict[str, str] = {
    "LOGIN_IP_LIMIT": "5",
    "LOGIN_IP_WINDOW_S": "60",
    "LOGIN_ACCOUNT_LIMIT": "10",
    "LOGIN_ACCOUNT_WINDOW_S": "900",
    "LOGIN_ACCOUNT_GLOBAL_LIMIT": "100",
    "LOGIN_ACCOUNT_GLOBAL_WINDOW_S": "3600",
    "LOGIN_LOCK_AFTER": "20",
    "REFRESH_IP_LIMIT": "60",
    "RESET_IP_LIMIT": "10",
    "FORGOT_IP_LIMIT": "5",
    "LOGOUT_IP_LIMIT": "30",
    "REFRESH_REUSE_GRACE_S": "10",
    "REFRESH_ABSOLUTE_TTL_DAYS": "30",
    "ALLOW_INSECURE_COOKIE": "false",
    "COOKIE_SECURE": "false",
}


def test_sin_variables_del_primer_admin() -> None:
    """M-8: `ADMIN_*` viven en `.env.seed` (solo `tools`); el ejemplo del api no las trae."""
    claves = _claves()
    assert "ADMIN_EMAIL" not in claves and "ADMIN_INITIAL_PASSWORD" not in claves
    assert {"ADMIN_EMAIL", "ADMIN_INITIAL_PASSWORD"} <= NON_API_ENV_VARS


def test_las_variables_nuevas_van_activas_con_sus_valores() -> None:
    """E9: `test_env_example` ignora comentarios, así que cada variable nueva es una línea
    activa con el valor de producción."""
    claves = _claves()
    for nombre, valor in NUEVAS_ACTIVAS.items():
        assert claves.get(nombre) == valor, nombre
    assert "AUTH_ALLOWED_ORIGINS" in claves
    assert int(claves["LOGIN_MIN_DURATION_MS"]) > 0


def test_allow_insecure_cookie_documenta_el_riesgo_p7() -> None:
    """E3/E9: el comentario junto a `ALLOW_INSECURE_COOKIE` nombra el riesgo aceptado P7."""
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("ALLOW_INSECURE_COOKIE=")]
    assert len(indices) == 1, "ALLOW_INSECURE_COOKIE debe ir una vez como línea activa"
    indice = indices[0]
    comentario = " ".join(
        linea for linea in lineas[max(0, indice - 4) : indice] if linea.startswith("#")
    )
    assert "P7" in comentario


# S3-W0-2 · tiempos de espera de la base (S3-D43) y topes por usuario (S3-D76, E10) ---------

ACTIVAS_S3_W0_2: dict[str, str] = {
    "DB_LOCK_TIMEOUT_MS": "10000",
    "DB_STATEMENT_TIMEOUT_MS": "30000",
    "DB_IDLE_IN_TX_TIMEOUT_MS": "60000",
    "USER_WRITE_LIMIT_PER_MIN": "30",
    "USER_ADMIN_WRITE_LIMIT_PER_MIN": "30",
    "USER_MEMBERS_WRITE_LIMIT_PER_MIN": "60",
    "USER_SEARCH_LIMIT_PER_MIN": "60",
    "USER_DETAIL_LIMIT_PER_MIN": "120",
    "USER_REVEAL_LIMIT_PER_MIN": "30",
    "USER_REVEAL_LIMIT_PER_HOUR": "200",
    "USER_REVEAL_LIMIT_PER_DAY": "600",
}


def test_las_once_variables_de_s3_w0_2_van_activas_con_sus_valores() -> None:
    """E10: las once variables nuevas son líneas activas (no comentadas) con el valor por
    defecto de `Settings`; V4 las multiplica por 100 en el bloque E2E (E15)."""
    claves = _claves()
    faltan = {n: claves.get(n) for n, v in ACTIVAS_S3_W0_2.items() if claves.get(n) != v}
    assert faltan == {}, f"valores distintos o ausentes en .env.example: {faltan}"
    for nombre, valor in ACTIVAS_S3_W0_2.items():
        assert Settings.model_fields[nombre].default == int(valor), nombre


ACTIVAS_S4A_B3: dict[str, str] = {
    "USER_READ_LIMIT_PER_MIN": "120",
    "USER_AUDIT_VERIFY_LIMIT_PER_MIN": "3",
    "USER_AUDIT_VERIFY_LIMIT_PER_HOUR": "20",
}


def test_las_tres_variables_de_s4a_b3_van_activas_con_sus_valores() -> None:
    """S4A-D65: las tres variables nuevas son líneas activas con el valor por defecto de
    `Settings` (V4 y el job `e2e-stack` de la CI las multiplican por 100, E9)."""
    claves = _claves()
    faltan = {n: claves.get(n) for n, v in ACTIVAS_S4A_B3.items() if claves.get(n) != v}
    assert faltan == {}, f"valores distintos o ausentes en .env.example: {faltan}"
    for nombre, valor in ACTIVAS_S4A_B3.items():
        assert Settings.model_fields[nombre].default == int(valor), nombre


def test_el_comentario_de_s4a_b3_cita_m1_m3_y_el_conteo_de_cubetas() -> None:
    """E9: el comentario del bloque dice de dónde vienen (S4A-B3, M-1 y M-3) y el conteo nuevo
    del catálogo (16 cubetas y 15 variables `USER_*` desde S5-D81)."""
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("USER_READ_LIMIT_PER_MIN=")]
    assert len(indices) == 1, "USER_READ_LIMIT_PER_MIN debe ir una vez como línea activa"
    comentario = " ".join(
        linea for linea in lineas[max(0, indices[0] - 4) : indices[0]] if linea.startswith("#")
    )
    assert "S4A-B3, M-1 y M-3" in comentario
    assert "16 cubetas" in comentario and "15 variables" in comentario  # S5-D81
    activas = [n for n in _claves() if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 15, activas  # 11 de S4A y las 4 de S5-D81


def test_los_tiempos_de_espera_documentan_que_cero_solo_es_del_cli() -> None:
    """W0-2.3: el comentario de las `DB_*` dice que 0 desactiva y que es solo para el CLI con
    `--db-timeouts off`."""
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("DB_LOCK_TIMEOUT_MS=")]
    assert len(indices) == 1, "DB_LOCK_TIMEOUT_MS debe ir una vez como línea activa"
    comentario = " ".join(
        linea for linea in lineas[max(0, indices[0] - 6) : indices[0]] if linea.startswith("#")
    )
    assert "0" in comentario and "--db-timeouts off" in comentario


# S4B-W0-1 · segundo archivo de ejemplo (S4B-D79, E7): variables de operación -----------------

ACTIVAS_S4B_W0_1: dict[str, str] = {
    "BACKUP_KEEP_DAYS": "14",
    "BACKUP_CRON": "0 2 * * *",
    "BACKUP_AGE_RECIPIENT": "",
    "BACKUP_AGE_VERIFY_RECIPIENT": "",
    "BACKUP_RCLONE_REMOTE": "",
    "RCLONE_CONFIG_APEX_TYPE": "s3",
    "RCLONE_CONFIG_APEX_PROVIDER": "",
    "RCLONE_CONFIG_APEX_ENDPOINT": "",
    "RCLONE_CONFIG_APEX_ACCESS_KEY_ID": "",
    "RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY": "",
    "BACKUP_SIGN_PUBKEY": "",
    "BACKUP_SIGN_KEY_FILE": "",
    "BACKUP_VERIFY_IDENTITY_FILE": "",
    "DEPLOY_HEALTH_TIMEOUT": "120",
    "APEX_API_DB_PASSWORD": "cambiar-esto",
    "APEX_WORKER_DB_PASSWORD": "cambiar-esto",
    "APEX_BACKUP_DB_PASSWORD": "cambiar-esto",
    "APEX_SUBNET": "172.30.0.0/24",
    "APEX_IP_RANGE": "172.30.0.128/25",
    "APEX_WEB_IP": "172.30.0.10",
    "APEX_CUSTODY_SUBNET": "172.30.1.0/24",
    "MIGRATE_DB_USER": "apex_owner",
}


def test_el_ejemplo_de_operacion_existe() -> None:
    assert EJEMPLO_OPS.is_file()


def test_las_variables_de_s4b_w0_1_van_activas_con_sus_valores() -> None:
    """S4B-D79: las variables nuevas de operación son líneas activas en `.env.ops.example`."""
    claves = _claves(EJEMPLO_OPS)
    distintas = {n: claves.get(n) for n, v in ACTIVAS_S4B_W0_1.items() if claves.get(n) != v}
    assert distintas == {}, f"valores distintos o ausentes en .env.ops.example: {distintas}"


def test_las_claves_de_operacion_estan_en_non_api_env_vars() -> None:
    # DATABASE_URL es un campo de Settings (S4B-D79, E7): se documenta aqui pero no es ajena.
    assert set(_claves(EJEMPLO_OPS)) <= NON_API_ENV_VARS | set(Settings.model_fields)


def test_sin_claves_repetidas_entre_los_dos_ejemplos() -> None:
    assert set(_claves()) & set(_claves(EJEMPLO_OPS)) == set()


def test_el_ejemplo_de_operacion_no_trae_secretos_reales() -> None:
    import re

    texto = EJEMPLO_OPS.read_text(encoding="utf-8")
    for clave, valor in _claves(EJEMPLO_OPS).items():
        if clave.endswith(("PASSWORD", "SECRET", "TOKEN", "KEY", "SECRET_ACCESS_KEY")):
            assert valor == "" or "cambiar-esto" in valor, f"{clave} parece llevar un valor real"
        assert not re.fullmatch(r"[A-Za-z0-9+/=_-]{43,}", valor), f"{clave} parece un secreto real"
        assert not valor.startswith("age1"), f"{clave} lleva un destinatario real"
    assert "-----BEGIN" not in texto
    assert "AGE-SECRET-KEY-" not in texto


# S4B-W0-3 (S4B-D56, S4B-D79, E7): el recorte de `.env.example` ------------------------------

PREFIJOS_DE_OPERACION = ("POSTGRES_", "RCLONE_", "BACKUP_")


def test_env_example_sin_secretos_de_operacion() -> None:
    """H-1: `.env` (el que leen api y worker por `env_file`) no trae contraseñas ni nada ajeno."""
    claves = _claves()
    ajenas = [
        c
        for c in claves
        if c.startswith(PREFIJOS_DE_OPERACION)
        or c.endswith("_DB_PASSWORD")
        or c in ("DATABASE_URL", "TEST_DATABASE_URL")
    ]
    assert ajenas == [], f"deben vivir en .env.ops.example: {ajenas}"
    activas = [
        linea
        for linea in EJEMPLO.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]
    assert not [linea for linea in activas if "DATABASE_URL=" in linea]


def test_las_variables_de_operacion_de_s4b_w0_3_estan_en_env_ops_example() -> None:
    claves = _claves(EJEMPLO_OPS)
    esperadas = (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "WEB_PORT",
        "API_PORT",
        "DB_PORT",
        "DB_TEST_PORT",
    )
    assert [n for n in esperadas if n not in claves] == []
    assert "cambiar-esto" in claves["POSTGRES_PASSWORD"]
    assert claves["DATABASE_URL"].startswith("postgresql+asyncpg://")
    assert "127.0.0.1" in claves["TEST_DATABASE_URL"], "siempre 127.0.0.1, no localhost"


def test_migrate_on_startup_va_activo_y_documenta_que_produccion_lo_fija_en_false() -> None:
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("MIGRATE_ON_STARTUP=")]
    assert len(indices) == 1, "MIGRATE_ON_STARTUP debe ir una vez como línea activa"
    assert lineas[indices[0]] == "MIGRATE_ON_STARTUP=false"
    comentario = " ".join(
        linea for linea in lineas[max(0, indices[0] - 4) : indices[0]] if linea.startswith("#")
    )
    assert "en producción lo fija Compose en `false`" in comentario
    assert Settings.model_fields["MIGRATE_ON_STARTUP"].default is False


def test_la_cabecera_de_env_example_remite_al_archivo_de_operacion() -> None:
    cabecera = "\n".join(EJEMPLO.read_text(encoding="utf-8").splitlines()[:6])
    assert ".env.ops.example" in cabecera
    assert "DATABASE_URL" in cabecera, "dice que DATABASE_URL ya no vive aqui"


def test_import_dir_documentada_con_el_valor_de_la_imagen() -> None:
    """S4B-D90: `IMPORT_DIR` es campo de `Settings` y la carpeta de la imagen es `/data/imports`."""
    assert _claves()["IMPORT_DIR"] == "/data/imports"


def test_backup_dir_vive_en_env_ops_example_y_no_en_env_example() -> None:
    """S4B-B2 (S4B-D25): `BACKUP_*` es de operación; `Settings.BACKUP_DIR` se documenta allí."""
    assert _claves(EJEMPLO_OPS)["BACKUP_DIR"] == "/data/backups"
    assert "BACKUP_DIR" not in _claves()
    assert "BACKUP_DIR" in Settings.model_fields


# S5-W0-3 (S5-D44, S5-D81, S5-D98): reparto de las variables nuevas -------------------------

NO_SECRETAS_S5: dict[str, str] = {
    "OPENBAO_ADDR": "http://openbao:8200",
    "OPENBAO_TIMEOUT_S": "5",
    "CRYPTO_RECOVERY_POLL_S": "20",
    "SMTP_PORT": "587",
    "SMTP_TLS_MODE": "starttls",
    "TELEGRAM_API_BASE": "https://api.telegram.org",
    "NOTIFY_MAX_ATTEMPTS": "3",
    "NOTIFY_NET_TIMEOUT_S": "10",
    "EXPORT_MAX_ROWS": "20000",
    "USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN": "30",
    "USER_EXPORT_LIMIT_PER_MIN": "2",
    "USER_EXPORT_LIMIT_PER_HOUR": "6",
    "USER_EXPORT_LIMIT_PER_DAY": "20",
}
"""Líneas activas de `.env.example` con el valor por defecto de `Settings`."""

NO_SECRETAS_S5_VACIAS: tuple[str, ...] = (
    "OPENBAO_TOKEN_FILE",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_FROM",
    "TELEGRAM_CHAT_ID",
)
"""También en `.env.example` (no son secretas), con el valor vacío o de ejemplo."""

SOLO_EN_OPERACION_S5: tuple[str, ...] = (
    "SMTP_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "APEX_CUSTODY_SUBNET",
    "MIGRATE_DB_USER",
    "TOOLS_DB_USER",
    "BACKUP_SIGN_PUBKEY",
)

CUATRO_USER_S5: tuple[str, ...] = (
    "USER_NOTIFICATIONS_WRITE_LIMIT_PER_MIN",
    "USER_EXPORT_LIMIT_PER_MIN",
    "USER_EXPORT_LIMIT_PER_HOUR",
    "USER_EXPORT_LIMIT_PER_DAY",
)
CUATRO_BUCKETS_S5: tuple[str, ...] = (
    "notifications-write",
    "export",
    "export-hour",
    "export-day",
)
CI_YML = RAIZ / ".github" / "workflows" / "ci.yml"


def test_lo_no_secreto_de_s5_va_en_env_example_con_su_valor_por_defecto() -> None:
    claves = _claves()
    distintas = {n: claves.get(n) for n, v in NO_SECRETAS_S5.items() if claves.get(n) != v}
    assert distintas == {}, f"valores distintos o ausentes en .env.example: {distintas}"
    for nombre, valor in NO_SECRETAS_S5.items():
        assert str(Settings.model_fields[nombre].default) == valor, nombre
    ausentes = [n for n in NO_SECRETAS_S5_VACIAS if n not in claves]
    assert ausentes == [], f"faltan en .env.example: {ausentes}"


def test_el_token_de_openbao_del_ejemplo_apunta_a_una_ruta_no_a_un_valor() -> None:
    valor = _claves()["OPENBAO_TOKEN_FILE"]
    assert valor == "" or valor.startswith("/run/apex/"), valor


def test_lo_secreto_y_de_operacion_de_s5_va_en_env_ops_example() -> None:
    ops = _claves(EJEMPLO_OPS)
    ausentes = [n for n in SOLO_EN_OPERACION_S5 if n not in ops]
    assert ausentes == [], f"faltan en .env.ops.example: {ausentes}"
    en_publico = [n for n in SOLO_EN_OPERACION_S5 if n in _claves()]
    assert en_publico == [], f"no deben estar en .env.example: {en_publico}"


@pytest.mark.parametrize("nombre", ["SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN"])
def test_los_secretos_de_s5_van_vacios_o_con_cambiar_esto_en_el_ejemplo_de_operacion(
    nombre: str,
) -> None:
    valor = _claves(EJEMPLO_OPS)[nombre]
    assert valor == "" or "cambiar-esto" in valor, f"{nombre} parece llevar un valor real"


def test_sin_claves_repetidas_dentro_de_cada_ejemplo() -> None:
    for ruta in (EJEMPLO, EJEMPLO_OPS):
        nombres = [
            linea.split("=", 1)[0].strip()
            for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.lstrip().startswith("#") and "=" in linea
        ]
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        assert repetidas == [], f"{ruta.name}: claves repetidas {repetidas}"


def test_el_reparto_s5_no_repite_claves_entre_los_dos_ejemplos() -> None:
    comunes = set(_claves()) & set(_claves(EJEMPLO_OPS))
    assert comunes == set()
    todas = set(NO_SECRETAS_S5) | set(NO_SECRETAS_S5_VACIAS) | set(SOLO_EN_OPERACION_S5)
    assert todas <= set(_claves()) | set(_claves(EJEMPLO_OPS))


def test_el_comentario_del_catalogo_dice_16_cubetas_y_15_variables() -> None:
    """S5-D81: el catálogo pasa a 16 cubetas y 15 variables `USER_*`."""
    texto = EJEMPLO.read_text(encoding="utf-8")
    comentario = " ".join(linea for linea in texto.splitlines() if linea.startswith("#"))
    assert "16 cubetas" in comentario and "15 variables" in comentario
    assert "12 cubetas" not in comentario and "11 variables" not in comentario
    activas = [n for n in _claves() if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 15, activas
    assert set(CUATRO_USER_S5) <= set(activas)


def test_las_cuatro_cubetas_nuevas_estan_en_user_limits_con_sus_ventanas() -> None:
    from app.core.ratelimit import USER_LIMITS

    assert [b for b in CUATRO_BUCKETS_S5 if b not in USER_LIMITS] == []
    assert USER_LIMITS["notifications-write"] == (30, 60)
    assert USER_LIMITS["export"] == (2, 60)
    assert USER_LIMITS["export-hour"] == (6, 3600)
    assert USER_LIMITS["export-day"] == (20, 86400)
    assert len(USER_LIMITS) == 16


def test_las_cuatro_cubetas_nuevas_estan_pendientes_de_ruta_en_el_catalogo_de_pruebas() -> None:
    from tests.architecture.test_user_limits_catalog import CLAVES_SIN_RUTA_TODAVIA

    assert set(CUATRO_BUCKETS_S5) <= CLAVES_SIN_RUTA_TODAVIA


def test_user_limits_from_alimenta_las_cuatro_cubetas_desde_settings() -> None:
    from app.cli import export_settings
    from app.core.ratelimit import user_limits_from

    topes = user_limits_from(export_settings())
    assert topes["notifications-write"] == (30, 60)
    assert topes["export"] == (2, 60)
    assert topes["export-hour"] == (6, 3600)
    assert topes["export-day"] == (20, 86400)


def test_ci_sube_las_quince_variables_user_y_cuenta_quince() -> None:
    """S5-D98: el `sed` del job e2e-stack sube también las cuatro nuevas y el conteo es 15."""
    texto = CI_YML.read_text(encoding="utf-8")
    assert '[ "$subidas" = "15" ]' in texto, "el conteo de subidas debe ser 15"
    assert "se esperaban 15 cubetas USER_* subidas" in texto
    for nombre in CUATRO_USER_S5:
        assert texto.count(nombre) >= 2, f"{nombre} debe estar en el sed y en la regex del conteo"
