"""`opaque_token_matches` (S8-C1, S8-D30, L-1): comparación en tiempo constante del SHA-256."""

from __future__ import annotations

from app.core.security import hash_opaque_token, new_opaque_token, opaque_token_matches


def test_igual() -> None:
    token = new_opaque_token()
    assert opaque_token_matches(token, hash_opaque_token(token)) is True


def test_distinto() -> None:
    token = new_opaque_token()
    assert opaque_token_matches(new_opaque_token(), hash_opaque_token(token)) is False
    assert opaque_token_matches(token, hash_opaque_token(token).upper()) is False


def test_mas_de_128_falso() -> None:
    largo = "a" * 129
    assert opaque_token_matches(largo, hash_opaque_token(largo)) is False
    justo = "a" * 128
    assert opaque_token_matches(justo, hash_opaque_token(justo)) is True


def test_no_ascii_falso() -> None:
    assert opaque_token_matches("contraseña-ñ", "0" * 64) is False
    assert opaque_token_matches("abc", "ñ" * 64) is False


def test_vacio_y_hash_vacio_falso() -> None:
    assert opaque_token_matches("", hash_opaque_token("")) is False
    assert opaque_token_matches("abc", "") is False
