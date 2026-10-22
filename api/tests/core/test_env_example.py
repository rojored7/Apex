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
