"""`.env.example` documenta toda variable de `Settings` y no trae secretos.

US-007 (T1 y T2) y US-011 (T8).
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import NON_API_ENV_VARS, Settings

RAIZ = Path(__file__).resolve().parents[3]
EJEMPLO = RAIZ / ".env.example"


def _claves() -> dict[str, str]:
    claves: dict[str, str] = {}
    for linea in EJEMPLO.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        claves[clave.strip()] = valor.strip()
    return claves


def test_el_ejemplo_existe() -> None:
    assert EJEMPLO.is_file()


def test_toda_variable_de_settings_esta_documentada() -> None:
    claves = _claves()
    faltan = [nombre for nombre in Settings.model_fields if nombre not in claves]
    assert faltan == [], f"faltan en .env.example: {faltan}"


def test_toda_clave_ajena_al_api_esta_en_non_api_env_vars() -> None:
    claves = _claves()
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
    assert "cambiar-esto" in claves["DATABASE_URL"]


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
