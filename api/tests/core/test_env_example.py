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


# S7-D23: la ruta de la llave de firma NO lleva línea en `.env` (vacía vale `Path(".")` y una ruta
# bajo `custody/` reabre el residual de ADR-006); se documenta solo en un comentario.
SIN_LINEA: frozenset[str] = frozenset({"CRYPTO_LOCAL_SIGNING_KEY_PATH"})


def test_firma_sin_linea_documentada_en_comentario() -> None:
    texto = EJEMPLO.read_text(encoding="utf-8")
    assert "CRYPTO_LOCAL_SIGNING_KEY_PATH" not in _claves()
    assert "# CRYPTO_LOCAL_SIGNING_KEY_PATH" in texto
    assert "/run/apex/keys/sign/sign-ed25519.key" in texto


def test_toda_variable_de_settings_esta_documentada() -> None:
    claves = {**_claves(), **_claves(EJEMPLO_OPS)}  # S4B-D79: DATABASE_URL vive en el de operacion
    faltan = [
        nombre
        for nombre in Settings.model_fields
        if nombre not in claves and nombre not in SIN_LINEA
    ]
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
    del catálogo (28 cubetas y 27 variables `USER_*` desde S9-D17; antes 16 y 15 de S5-D81)."""
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("USER_READ_LIMIT_PER_MIN=")]
    assert len(indices) == 1, "USER_READ_LIMIT_PER_MIN debe ir una vez como línea activa"
    comentario = " ".join(
        linea for linea in lineas[max(0, indices[0] - 4) : indices[0]] if linea.startswith("#")
    )
    assert "S4A-B3, M-1 y M-3" in comentario
    assert "28 cubetas" in comentario and "27 variables" in comentario  # S9-D17
    activas = [n for n in _claves() if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 27, activas  # 11 de S4A, 4 de S5, 7 de S6, 2 de S7, 2 de S8 y 1 de S9


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
    "APEX_OWNER_DB_PASSWORD": "cambiar-esto",
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


def test_el_comentario_del_catalogo_dice_28_cubetas_y_27_variables() -> None:
    """S9-D17: el catálogo pasa a 28 cubetas y 27 variables `USER_*` (antes 27 y 26, S8-D22)."""
    texto = EJEMPLO.read_text(encoding="utf-8")
    comentario = " ".join(linea for linea in texto.splitlines() if linea.startswith("#"))
    assert "28 cubetas" in comentario and "27 variables" in comentario
    assert "27 cubetas" not in comentario and "26 variables" not in comentario
    assert "25 cubetas" not in comentario and "24 variables" not in comentario
    assert "23 cubetas" not in comentario and "22 variables" not in comentario
    assert "16 cubetas" not in comentario and "15 variables" not in comentario
    assert "12 cubetas" not in comentario and "11 variables" not in comentario
    activas = [n for n in _claves() if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 27, activas
    assert set(CUATRO_USER_S5) <= set(activas)
    assert set(SIETE_USER_S6) <= set(activas)


DOS_USER_S7: tuple[str, ...] = (
    "USER_CLASSES_WRITE_LIMIT_PER_MIN",
    "USER_ATTENDANCE_WRITE_LIMIT_PER_MIN",
)


DOS_USER_S8: tuple[str, ...] = (
    "USER_WODS_WRITE_LIMIT_PER_MIN",
    "USER_RESULTS_WRITE_LIMIT_PER_MIN",
)


def test_27_variables_user() -> None:
    """S7-D19, S8-D22 y S9-D17: `.env.example` documenta las variables de S7 (30 y 60), de S8 (30 y
    60) y la de S9 (30); el total es 27."""
    claves = _claves()
    assert [n for n in DOS_USER_S7 if n not in claves] == []
    assert claves["USER_CLASSES_WRITE_LIMIT_PER_MIN"] == "30"
    assert claves["USER_ATTENDANCE_WRITE_LIMIT_PER_MIN"] == "60"
    assert [n for n in DOS_USER_S8 if n not in claves] == []
    assert claves["USER_WODS_WRITE_LIMIT_PER_MIN"] == "30"
    assert claves["USER_RESULTS_WRITE_LIMIT_PER_MIN"] == "60"
    assert claves["USER_ATHLETES_WRITE_LIMIT_PER_MIN"] == "30"
    activas = [n for n in claves if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 27, activas


def test_las_cuatro_cubetas_nuevas_estan_en_user_limits_con_sus_ventanas() -> None:
    from app.core.ratelimit import USER_LIMITS

    assert [b for b in CUATRO_BUCKETS_S5 if b not in USER_LIMITS] == []
    assert USER_LIMITS["notifications-write"] == (30, 60)
    assert USER_LIMITS["export"] == (2, 60)
    assert USER_LIMITS["export-hour"] == (6, 3600)
    assert USER_LIMITS["export-day"] == (20, 86400)
    assert len(USER_LIMITS) == 28  # 16 de S5, 7 de S6-D57, 2 de S7-D19, 2 de S8-D22 y 1 de S9-D17


def test_las_cuatro_cubetas_nuevas_ya_tienen_ruta_en_el_catalogo_de_pruebas() -> None:
    """S5-B5 dio ruta a `notifications-write` y B12 a las tres `export*` (S5-D98, S5-D150); desde
    S6-W0-5 `CLAVES_SIN_RUTA_TODAVIA` guarda solo las siete de S6-D57 hasta que cada slice les dé
    ruta."""
    from tests.architecture.test_user_limits_catalog import CLAVES_SIN_RUTA_TODAVIA

    # S6-B3: `cbom-export` ya tiene ruta (`GET /crypto/cbom`); S6-C2: `attachments-upload`
    # (`POST /members/{id}/attachments`); S6-C4: las tres de `GET /attachments/{id}`.
    con_ruta = {
        "cbom-export",
        "attachments-upload",
        "attachments-photo",
        "attachments-download",
        "attachments-download-hour",
        "keys-rotate",  # S6-R1: `POST /crypto/keys/{key_id}/rotate`
        "keys-rotate-hour",
    }
    # S7-D19: las dos de S7 se registraron en W0-4 sin ruta; `classes-write` la tiene desde A2
    # (`/class-slots`) y `attendance-write` desde C1 (`POST /attendance`): no queda ninguna.
    assert (
        CLAVES_SIN_RUTA_TODAVIA & frozenset(SIETE_BUCKETS_S6)
        == frozenset(SIETE_BUCKETS_S6) - con_ruta
    )
    # S8-D22: las dos de S8 se registran sin ruta; A1 y B1 les dan la suya.
    # S8-B1: wods-write y results-write con ruta; S9-A1: `athletes-write` ya tiene la suya
    # (`POST /athletes/{member_id}/metrics`) y el catálogo entero vuelve a tener ruta (P-CAT 2).
    assert CLAVES_SIN_RUTA_TODAVIA == frozenset()
    from app.core.ratelimit import USER_LIMITS

    assert {"classes-write", "attendance-write"} <= set(USER_LIMITS)
    assert not set(CUATRO_BUCKETS_S5) & CLAVES_SIN_RUTA_TODAVIA


def test_user_limits_from_alimenta_las_cuatro_cubetas_desde_settings() -> None:
    from app.cli import export_settings
    from app.core.ratelimit import user_limits_from

    topes = user_limits_from(export_settings())
    assert topes["notifications-write"] == (30, 60)
    assert topes["export"] == (2, 60)
    assert topes["export-hour"] == (6, 3600)
    assert topes["export-day"] == (20, 86400)


def test_ci_sube_las_veintisiete_variables_user_y_cuenta_veintisiete() -> None:
    """S5-D98, S6-D57, S7-D19, S8-D22, S9-D17: el `sed` del job e2e-stack sube también las siete de
    S6, las dos de S7, las dos de S8 y la de S9; el conteo es 27."""
    texto = CI_YML.read_text(encoding="utf-8")
    assert '[ "$subidas" = "27" ]' in texto, "el conteo de subidas debe ser 27"
    assert "se esperaban 27 cubetas USER_* subidas" in texto
    assert "USER_ATHLETES_WRITE_LIMIT_PER_MIN=3000" in texto
    assert "USER_WODS_WRITE_LIMIT_PER_MIN=3000" in texto
    assert "USER_RESULTS_WRITE_LIMIT_PER_MIN=6000" in texto
    assert "USER_CLASSES_WRITE_LIMIT_PER_MIN=3000" in texto
    assert "USER_ATTENDANCE_WRITE_LIMIT_PER_MIN=6000" in texto
    for nombre in (
        *CUATRO_USER_S5,
        *SIETE_USER_S6,
        *DOS_USER_S7,
        *DOS_USER_S8,
        "USER_ATHLETES_WRITE_LIMIT_PER_MIN",
    ):
        assert texto.count(nombre) >= 2, f"{nombre} debe estar en el sed y en la regex del conteo"


def test_tv_ip_y_token_documentadas() -> None:
    """S8-D33: `.env.example` documenta `TV_IP_LIMIT` (12) y `TV_TOKEN_LIMIT` (30) como líneas
    activas, y las dos son campos de `Settings` con esos valores por defecto."""
    from app.core.config import Settings

    claves = _claves()
    assert claves["TV_IP_LIMIT"] == "12"
    assert claves["TV_TOKEN_LIMIT"] == "30"  # noqa: S105 (un tope, no una contraseña)
    assert Settings.model_fields["TV_IP_LIMIT"].default == 12
    assert Settings.model_fields["TV_TOKEN_LIMIT"].default == 30


def test_ci_fija_tv_ip_y_token_en_120_dentro_de_la_cota() -> None:
    """Hallazgo 8 de la crítica 1: `TV_IP_LIMIT` y `TV_TOKEN_LIMIT` tienen cota de 1 a 120; el
    job e2e-stack los fija en 120 con una línea de `sed` propia, no dentro de la línea de los
    límites por IP (`=1000` rompería la cota y el api no arrancaría)."""
    texto = CI_YML.read_text(encoding="utf-8")
    assert "-e 's/^(TV_IP_LIMIT|TV_TOKEN_LIMIT)=.*/\\1=120/'" in texto
    for linea in texto.splitlines():
        if "TV_IP_LIMIT" in linea and "s/^" in linea:
            assert "=1000" not in linea, linea


# --- S5-W0-4: apex_owner NOSUPERUSER (S5-D6, D89, D96; M-12) ------------------------------------


def test_la_contrasena_de_apex_owner_va_en_env_ops_example_con_cambiar_esto() -> None:
    ops = _claves(EJEMPLO_OPS)
    assert ops.get("APEX_OWNER_DB_PASSWORD") == "cambiar-esto"
    assert "APEX_OWNER_DB_PASSWORD" not in _claves(), "es de operacion, no de .env.example"


def test_los_roles_de_migrate_y_tools_valen_apex_owner_en_el_ejemplo_de_operacion() -> None:
    ops = _claves(EJEMPLO_OPS)
    assert ops.get("MIGRATE_DB_USER") == "apex_owner"
    assert ops.get("TOOLS_DB_USER") == "apex_owner"


def test_apex_owner_db_password_es_ajena_al_api() -> None:
    assert "APEX_OWNER_DB_PASSWORD" in NON_API_ENV_VARS
    assert "APEX_OWNER_DB_PASSWORD" not in Settings.model_fields


# --- Rojo S6-W0-5 (S6-D47, D57, D65, D77): reparto de las variables nuevas ----------------------

NO_SECRETAS_S6: dict[str, str] = {
    "STORAGE_PROVIDER": "local",
    "S3_ENABLE_PRODUCTION": "false",
    "ALLOW_DOMAIN_PORT": "false",
    "USER_ATTACHMENTS_UPLOAD_LIMIT_PER_MIN": "10",
    "USER_ATTACHMENTS_PHOTO_LIMIT_PER_MIN": "600",
    "USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_MIN": "30",
    "USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_HOUR": "200",
    "USER_KEYS_ROTATE_LIMIT_PER_MIN": "3",
    "USER_KEYS_ROTATE_LIMIT_PER_HOUR": "10",
    "USER_CBOM_EXPORT_LIMIT_PER_MIN": "2",
}
"""Líneas activas de `.env.example` con el valor por defecto de `Settings`."""

NO_SECRETAS_S6_VACIAS: tuple[str, ...] = (
    "S3_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_REGION",
    "S3_ACCESS_KEY_ID",
    "APEX_DOMAIN",
)
"""También en `.env.example` (no son secretas), vacías por defecto (almacén local, sin dominio)."""

SIETE_USER_S6: tuple[str, ...] = (
    "USER_ATTACHMENTS_UPLOAD_LIMIT_PER_MIN",
    "USER_ATTACHMENTS_PHOTO_LIMIT_PER_MIN",
    "USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_MIN",
    "USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_HOUR",
    "USER_KEYS_ROTATE_LIMIT_PER_MIN",
    "USER_KEYS_ROTATE_LIMIT_PER_HOUR",
    "USER_CBOM_EXPORT_LIMIT_PER_MIN",
)
SIETE_BUCKETS_S6: dict[str, tuple[int, int]] = {
    "attachments-upload": (10, 60),
    "attachments-photo": (600, 60),
    "attachments-download": (30, 60),
    "attachments-download-hour": (200, 3600),
    "keys-rotate": (3, 60),
    "keys-rotate-hour": (10, 3600),
    "cbom-export": (2, 60),
}
SEIS_CADDY_S6: tuple[str, ...] = (
    "APEX_CADDY_IP",
    "APEX_TLS_ISSUER",
    "APEX_ACME_EMAIL",
    "APEX_ACME_CA",
    "APEX_HSTS_MAX_AGE",
    "TLS_PORT",
)


def test_lo_no_secreto_de_s6_va_en_env_example_con_su_valor_por_defecto() -> None:
    claves = _claves()
    distintas = {n: claves.get(n) for n, v in NO_SECRETAS_S6.items() if claves.get(n) != v}
    assert distintas == {}, f"valores distintos o ausentes en .env.example: {distintas}"
    for nombre, valor in NO_SECRETAS_S6.items():
        assert nombre in Settings.model_fields, f"{nombre} aún no es un campo de Settings"
        por_defecto = Settings.model_fields[nombre].default
        assert str(por_defecto).lower() == valor, nombre
    ausentes = [n for n in NO_SECRETAS_S6_VACIAS if n not in claves]
    assert ausentes == [], f"faltan en .env.example: {ausentes}"
    assert [n for n in NO_SECRETAS_S6_VACIAS if n not in Settings.model_fields] == []


def test_lo_secreto_y_de_caddy_de_s6_va_en_env_ops_example_y_no_en_el_publico() -> None:
    ops = _claves(EJEMPLO_OPS)
    esperadas = ("S3_SECRET_ACCESS_KEY", *SEIS_CADDY_S6)
    ausentes = [n for n in esperadas if n not in ops]
    assert ausentes == [], f"faltan en .env.ops.example: {ausentes}"
    en_publico = [n for n in esperadas if n in _claves()]
    assert en_publico == [], f"no deben estar en .env.example: {en_publico}"
    valor = ops["S3_SECRET_ACCESS_KEY"]
    assert valor == "" or "cambiar-esto" in valor, (
        "S3_SECRET_ACCESS_KEY parece llevar un valor real"
    )


def test_el_reparto_s6_no_repite_claves_entre_los_dos_ejemplos() -> None:
    comunes = set(_claves()) & set(_claves(EJEMPLO_OPS))
    assert comunes == set()
    todas = set(NO_SECRETAS_S6) | set(NO_SECRETAS_S6_VACIAS)
    assert todas <= set(_claves())


def test_las_siete_cubetas_de_s6_estan_en_user_limits_con_sus_ventanas() -> None:
    from app.core.ratelimit import USER_LIMITS

    assert [b for b in SIETE_BUCKETS_S6 if b not in USER_LIMITS] == []
    assert {b: USER_LIMITS[b] for b in SIETE_BUCKETS_S6 if b in USER_LIMITS} == SIETE_BUCKETS_S6


def test_user_limits_from_alimenta_las_siete_cubetas_de_s6_desde_settings() -> None:
    from app.cli import export_settings
    from app.core.ratelimit import user_limits_from

    topes = user_limits_from(export_settings())
    assert {b: topes.get(b) for b in SIETE_BUCKETS_S6} == SIETE_BUCKETS_S6


def test_las_siete_user_de_s6_son_campos_de_settings_con_el_tope_de_su_cubeta() -> None:
    faltan = [n for n in SIETE_USER_S6 if n not in Settings.model_fields]
    assert faltan == [], f"aún no son campos de Settings: {faltan}"
    por_defecto = [Settings.model_fields[n].default for n in SIETE_USER_S6]
    assert por_defecto == [10, 600, 30, 200, 3, 10, 2]


# S6-E1 (US-153): sin variables nuevas; los comentarios explican los dos modos -----------------


def _comentario_previo(nombre: str, lineas_previas: int = 8) -> str:
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith(f"{nombre}=")]
    assert len(indices) == 1, f"{nombre} debe ir una vez como línea activa"
    previas = lineas[max(0, indices[0] - lineas_previas) : indices[0]]
    return " ".join(linea for linea in previas if linea.startswith("#"))


def test_s6_e1_no_agrega_variables_al_ejemplo() -> None:
    claves = _claves()
    for nombre in ("PUBLIC_ORIGIN", "APEX_PUBLIC_ORIGIN", "PUBLIC_URL", "LAN_ORIGIN"):
        assert nombre not in claves
    for nombre in ("APEX_DOMAIN", "FRONT_BASE_URL", "COOKIE_SECURE", "ALLOW_INSECURE_COOKIE"):
        assert nombre in claves


def test_el_comentario_de_cookie_secure_explica_el_modo_dominio() -> None:
    comentario = _comentario_previo("COOKIE_SECURE")
    assert "APEX_DOMAIN" in comentario


def test_el_comentario_de_front_base_url_explica_que_con_dominio_es_https_del_dominio() -> None:
    comentario = _comentario_previo("FRONT_BASE_URL")
    assert "APEX_DOMAIN" in comentario and "https" in comentario


def test_el_comentario_de_apex_domain_cita_cookie_y_cors() -> None:
    comentario = _comentario_previo("APEX_DOMAIN", 6)
    assert "COOKIE_SECURE" in comentario and "CORS_ORIGINS" in comentario


def test_ci_siembra_benchmarks_tras_el_admin() -> None:
    """S8-A2 (hallazgo 9): el job e2e-stack siembra los benchmarks justo después del seed del
    primer admin y antes de las dependencias del front, para que la spec de F1 encuentre «Fran»."""
    texto = CI_YML.read_text(encoding="utf-8")
    orden = "$DC --profile tools run --rm tools seed-benchmarks"
    assert texto.count(orden) == 1
    seed = texto.index("tools seed --no-force-change")
    assert seed < texto.index(orden) < texto.index("name: dependencias del front")


def test_ci_deriva_records_tras_los_benchmarks() -> None:
    """S9-B6 (S9-D21): el job e2e-stack corre derive-records una vez, tras sembrar benchmarks."""
    texto = CI_YML.read_text(encoding="utf-8")
    orden = "$DC --profile tools run --rm tools derive-records"
    assert texto.count(orden) == 1
    sembrado = texto.index("$DC --profile tools run --rm tools seed-benchmarks")
    assert sembrado < texto.index(orden) < texto.index("name: dependencias del front")
