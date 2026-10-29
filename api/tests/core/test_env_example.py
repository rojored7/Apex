"""`.env.example` documenta toda variable de `Settings` y no trae secretos.

US-007 (T1 y T2) y US-011 (T8).
"""

from __future__ import annotations

from pathlib import Path

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
    del catálogo (12 cubetas y 11 variables `USER_*`)."""
    lineas = EJEMPLO.read_text(encoding="utf-8").splitlines()
    indices = [i for i, linea in enumerate(lineas) if linea.startswith("USER_READ_LIMIT_PER_MIN=")]
    assert len(indices) == 1, "USER_READ_LIMIT_PER_MIN debe ir una vez como línea activa"
    comentario = " ".join(
        linea for linea in lineas[max(0, indices[0] - 4) : indices[0]] if linea.startswith("#")
    )
    assert "S4A-B3, M-1 y M-3" in comentario
    assert "12 cubetas" in comentario and "11 variables" in comentario
    activas = [n for n in _claves() if n.startswith("USER_") and "_LIMIT_PER_" in n]
    assert len(activas) == 11, activas


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
