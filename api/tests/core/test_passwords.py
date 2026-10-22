"""argon2id, política N-10 y sin fugas en logs (US-032 T5, T6)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.core.security import (
    WeakPasswordError,
    configure_password_hasher,
    configure_password_policy,
    dummy_verify,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)

CLAVE = "Zanahoria-Lunar-42x"


@pytest.fixture(autouse=True)
def parametros_bajos() -> Iterator[None]:
    """Parámetros mínimos para que las pruebas corran rápido (nunca en producción)."""
    configure_password_hasher(time_cost=1, memory_cost_kib=8, parallelism=1)
    configure_password_policy(min_length=12)
    try:
        yield
    finally:
        configure_password_hasher(time_cost=3, memory_cost_kib=65536, parallelism=4)


def test_hash_es_argon2id_y_distinto_cada_vez() -> None:
    a, b = hash_password(CLAVE), hash_password(CLAVE)
    assert a.startswith("$argon2id$") and b.startswith("$argon2id$")
    assert a != b
    assert CLAVE not in a


def test_verify_correcta_incorrecta_y_hash_malformado() -> None:
    h = hash_password(CLAVE)
    assert verify_password(h, CLAVE) is True
    assert verify_password(h, CLAVE.upper()) is False
    assert verify_password("no-es-un-hash", CLAVE) is False
    assert verify_password("", CLAVE) is False


def test_needs_rehash_con_memoria_menor_y_hash_malformado() -> None:
    debil = hash_password(CLAVE)  # memory_cost=8
    configure_password_hasher(time_cost=1, memory_cost_kib=16, parallelism=1)
    assert needs_rehash(debil) is True
    assert needs_rehash(hash_password(CLAVE)) is False
    assert needs_rehash("basura") is True


@pytest.mark.parametrize("clave", ["abcdefghijk", "", "Once-Letras"])
def test_corta_lanza_too_short(clave: str) -> None:
    with pytest.raises(WeakPasswordError) as excinfo:
        validate_password_policy(clave)
    assert excinfo.value.reason == "too_short"
    assert clave == "" or clave not in str(excinfo.value)


@pytest.mark.parametrize(
    "clave", ["Contraseña123", "123456789012", "QWERTYUIOPAS", "ApexCrossFit1"]
)
def test_comun_en_otra_capitalizacion_lanza_too_common(clave: str) -> None:
    with pytest.raises(WeakPasswordError) as excinfo:
        hash_password(clave)
    assert excinfo.value.reason == "too_common"
    assert clave not in str(excinfo.value)


def test_doce_caracteres_no_comunes_pasa() -> None:
    validate_password_policy("casa-azul-19")
    assert hash_password("casa-azul-19").startswith("$argon2id$")


def test_politica_configurable() -> None:
    configure_password_policy(min_length=16)
    with pytest.raises(WeakPasswordError):
        validate_password_policy("casa-azul-19")
    configure_password_policy(min_length=12)


def test_dummy_verify_no_falla_y_tarda_como_una_real() -> None:
    dummy_verify(CLAVE)
    dummy_verify("")


def test_sin_contrasena_ni_hash_en_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        h = hash_password(CLAVE)
        verify_password(h, CLAVE)
        verify_password(h, "otra")
        with pytest.raises(WeakPasswordError) as excinfo:
            hash_password("corta")
    texto = caplog.text + str(excinfo.value)
    assert CLAVE not in texto and h not in texto and "corta" not in str(excinfo.value)


# S2-B2 · L-5 del Sprint 1, S2-D30: tope de 128 caracteres -------------------------------


def test_el_tope_de_longitud_es_128() -> None:
    from app.core.security import PASSWORD_MAX_LENGTH

    assert PASSWORD_MAX_LENGTH == 128


def test_128_caracteres_no_comunes_pasa() -> None:
    clave = "casa-azul-19" + "x" * 116
    assert len(clave) == 128
    validate_password_policy(clave)
    assert hash_password(clave).startswith("$argon2id$")


def test_129_caracteres_lanza_too_long_sin_repetir_la_clave() -> None:
    clave = "casa-azul-19" + "x" * 117
    assert len(clave) == 129
    with pytest.raises(WeakPasswordError) as excinfo:
        validate_password_policy(clave)
    assert excinfo.value.reason == "too_long"
    assert clave not in str(excinfo.value)
    with pytest.raises(WeakPasswordError) as al_hashear:
        hash_password(clave)
    assert al_hashear.value.reason == "too_long"


def test_too_long_se_revisa_antes_que_too_common() -> None:
    """Orden del blueprint: `too_long`, luego `too_short`, luego `too_common`."""
    with pytest.raises(WeakPasswordError) as excinfo:
        validate_password_policy("123456789012" * 11)  # 132 caracteres de un patrón común
    assert excinfo.value.reason == "too_long"
