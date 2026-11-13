"""`public_origin`, `validate_origins` y `cookie_secure` (S6-E1, US-153 criterios 4, 5 y 7; D28,
D65, D77; S4B-D154).

Las `Settings` se arman con `model_copy` (fixtures `settings_lan` y `settings_dominio` de
`tests/conftest.py`): así los valores incoherentes llegan a la función sin pasar por la carga.
"""

from __future__ import annotations

import pytest

from app.core.config import ConfigError, Settings, cookie_secure, public_origin, validate_origins
from tests.conftest import SettingsDeModo

# public_origin ----------------------------------------------------------------------------


def test_sin_dominio_el_origen_publico_es_front_base_url(settings_lan: SettingsDeModo) -> None:
    assert public_origin(settings_lan(FRONT_BASE_URL="http://192.168.1.20:8080")) == (
        "http://192.168.1.20:8080"
    )


def test_con_dominio_el_origen_publico_es_https_del_dominio(
    settings_dominio: SettingsDeModo,
) -> None:
    assert public_origin(settings_dominio()) == "https://apex.example.com"


def test_con_dominio_el_origen_publico_ignora_front_base_url(
    settings_dominio: SettingsDeModo,
) -> None:
    ajustes = settings_dominio(FRONT_BASE_URL="http://localhost")
    assert public_origin(ajustes) == "https://apex.example.com"


def test_con_puerto_el_origen_publico_lo_conserva(settings_dominio: SettingsDeModo) -> None:
    ajustes = settings_dominio(
        APEX_DOMAIN="apex.localhost:8443",
        ALLOW_DOMAIN_PORT=True,
        FRONT_BASE_URL="https://apex.localhost:8443",
    )
    assert public_origin(ajustes) == "https://apex.localhost:8443"


def test_el_origen_publico_nunca_lleva_ruta_ni_barra_final(
    settings_dominio: SettingsDeModo,
) -> None:
    origen = public_origin(settings_dominio())
    assert origen == origen.rstrip("/") and origen.count("/") == 2


# validate_origins: modo dominio ------------------------------------------------------------


def test_el_modo_dominio_coherente_no_falla(settings_dominio: SettingsDeModo) -> None:
    validate_origins(settings_dominio())


def test_el_modo_dominio_con_puerto_coherente_no_falla(settings_dominio: SettingsDeModo) -> None:
    validate_origins(
        settings_dominio(
            APEX_DOMAIN="apex.localhost:8443",
            ALLOW_DOMAIN_PORT=True,
            FRONT_BASE_URL="https://apex.localhost:8443",
        )
    )


def test_el_modo_dominio_admite_cors_origins_https(settings_dominio: SettingsDeModo) -> None:
    validate_origins(settings_dominio(CORS_ORIGINS=["https://otro.example.com"]))


def _falla_nombrando(ajustes: Settings, *nombres: str) -> ConfigError:
    with pytest.raises(ConfigError) as excinfo:
        validate_origins(ajustes)
    assert set(nombres) <= set(excinfo.value.invalid), str(excinfo.value)
    for nombre in nombres:
        assert nombre in str(excinfo.value)
    return excinfo.value


def test_cors_origins_con_http_falla_nombrando_la_variable(
    settings_dominio: SettingsDeModo,
) -> None:
    error = _falla_nombrando(
        settings_dominio(CORS_ORIGINS=["http://otro.example.com"]), "CORS_ORIGINS"
    )
    assert "otro.example.com" not in str(error), "el mensaje nombra la variable, no su valor"


def test_cors_origins_con_http_entre_varios_origenes_falla(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(
        settings_dominio(CORS_ORIGINS=["https://a.example.com", "http://b.example.com"]),
        "CORS_ORIGINS",
    )


@pytest.mark.parametrize(
    "front",
    ["http://apex.example.com", "https://otro.example.com", "https://apex.example.com:8443"],
)
def test_front_base_url_distinta_de_public_origin_falla_nombrando_la_variable(
    settings_dominio: SettingsDeModo, front: str
) -> None:
    _falla_nombrando(settings_dominio(FRONT_BASE_URL=front), "FRONT_BASE_URL")


def test_cookie_secure_false_con_dominio_falla_nombrando_la_variable(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(settings_dominio(COOKIE_SECURE=False), "COOKIE_SECURE")


def test_allow_insecure_cookie_con_dominio_falla_nombrando_la_variable(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(settings_dominio(ALLOW_INSECURE_COOKIE=True), "ALLOW_INSECURE_COOKIE")


def test_allow_insecure_cookie_no_rescata_cookie_secure_false_con_dominio(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(
        settings_dominio(COOKIE_SECURE=False, ALLOW_INSECURE_COOKIE=True),
        "COOKIE_SECURE",
        "ALLOW_INSECURE_COOKIE",
    )


def test_varios_problemas_con_dominio_se_nombran_todos(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(
        settings_dominio(
            CORS_ORIGINS=["http://a.example.com"],
            FRONT_BASE_URL="http://localhost",
            COOKIE_SECURE=False,
        ),
        "CORS_ORIGINS",
        "FRONT_BASE_URL",
        "COOKIE_SECURE",
    )


@pytest.mark.parametrize("entorno", ["dev", "production"])
def test_con_dominio_las_reglas_valen_en_cualquier_entorno(
    settings_dominio: SettingsDeModo, entorno: str
) -> None:
    _falla_nombrando(settings_dominio(ENV=entorno, COOKIE_SECURE=False), "COOKIE_SECURE")


# validate_origins: modo LAN (S4B-D154) ----------------------------------------------------


def test_el_modo_lan_coherente_no_falla(settings_lan: SettingsDeModo) -> None:
    validate_origins(settings_lan())


def test_sin_dominio_cors_origins_con_http_sigue_valido(settings_lan: SettingsDeModo) -> None:
    validate_origins(settings_lan(CORS_ORIGINS=["http://apex.local", "http://localhost:5173"]))


def test_sin_dominio_front_base_url_en_http_sigue_valida(settings_lan: SettingsDeModo) -> None:
    validate_origins(settings_lan(FRONT_BASE_URL="http://192.168.1.20"))


def test_sin_dominio_produccion_exige_cookie_secure(settings_lan: SettingsDeModo) -> None:
    _falla_nombrando(settings_lan(ENV="production", COOKIE_SECURE=False), "COOKIE_SECURE")


def test_sin_dominio_produccion_acepta_la_excepcion_p7(settings_lan: SettingsDeModo) -> None:
    validate_origins(
        settings_lan(ENV="production", COOKIE_SECURE=False, ALLOW_INSECURE_COOKIE=True)
    )


def test_sin_dominio_produccion_con_cookie_secure_no_falla(settings_lan: SettingsDeModo) -> None:
    validate_origins(settings_lan(ENV="production", COOKIE_SECURE=True))


def test_sin_dominio_en_desarrollo_la_cookie_sin_secure_no_falla(
    settings_lan: SettingsDeModo,
) -> None:
    validate_origins(settings_lan(ENV="dev", COOKIE_SECURE=False))


# cookie_secure ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", [True, False])
def test_cookie_secure_devuelve_la_variable_sin_dominio(
    settings_lan: SettingsDeModo, valor: bool
) -> None:
    assert cookie_secure(settings_lan(COOKIE_SECURE=valor)) is valor


@pytest.mark.parametrize("valor", [True, False])
def test_cookie_secure_devuelve_la_variable_con_dominio(
    settings_dominio: SettingsDeModo, valor: bool
) -> None:
    assert cookie_secure(settings_dominio(COOKIE_SECURE=valor)) is valor


# AUTH_ALLOWED_ORIGINS y mayúsculas (revisión de seguridad de S6-E1, M1 y L1) --------------------


def test_auth_allowed_origins_con_http_falla_con_dominio(settings_dominio: SettingsDeModo) -> None:
    _falla_nombrando(
        settings_dominio(AUTH_ALLOWED_ORIGINS=["http://apex.example.com"]), "AUTH_ALLOWED_ORIGINS"
    )


def test_auth_allowed_origins_sin_el_origen_publico_falla_con_dominio(
    settings_dominio: SettingsDeModo,
) -> None:
    _falla_nombrando(
        settings_dominio(AUTH_ALLOWED_ORIGINS=["https://otro.example.com"]), "AUTH_ALLOWED_ORIGINS"
    )


def test_auth_allowed_origins_con_el_origen_publico_o_vacia_no_falla(
    settings_dominio: SettingsDeModo,
) -> None:
    validate_origins(settings_dominio(AUTH_ALLOWED_ORIGINS=[]))
    validate_origins(
        settings_dominio(AUTH_ALLOWED_ORIGINS=["https://apex.example.com", "https://x.example.com"])
    )


def test_sin_dominio_auth_allowed_origins_con_http_sigue_valido(
    settings_lan: SettingsDeModo,
) -> None:
    validate_origins(settings_lan(AUTH_ALLOWED_ORIGINS=["http://localhost"]))


def test_el_host_del_dominio_se_normaliza_a_minusculas(settings_dominio: SettingsDeModo) -> None:
    ajustes = settings_dominio(
        APEX_DOMAIN="Apex.Example.COM", FRONT_BASE_URL="https://apex.example.com"
    )
    assert public_origin(ajustes) == "https://apex.example.com"
    validate_origins(ajustes)
