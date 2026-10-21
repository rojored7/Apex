"""Normalización del índice ciego (US-026 T6; N-02, irreversible con datos)."""

from __future__ import annotations

import pytest

from app.core.crypto.errors import CryptoError
from app.core.crypto.normalize import normalize_for_index


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (" 1.020.304 ", "1020304"),
        ("1020-304", "1020304"),
        ("1020\u2013304", "1020304"),
        ("José Pérez", "joseperez"),
        ("Ñandú\tÁ\u00a0B", "nanduab"),
        ("Ana.Perez@Mail.com", "anaperez@mailcom"),
        ("\uff21\uff22\uff23\uff11\uff12\uff13", "abc123"),
    ],
)
def test_generic(valor: str, esperado: str) -> None:
    assert normalize_for_index(valor, "generic") == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("300 123 4567", "3001234567"),
        ("+57 300 123 4567", "3001234567"),
        ("573001234567", "3001234567"),
        ("(300) 123-4567", "3001234567"),
        ("6011234567", "6011234567"),
        ("57 601 123 4567", "6011234567"),
        ("5712345", "5712345"),
    ],
)
def test_phone(valor: str, esperado: str) -> None:
    assert normalize_for_index(valor, "phone") == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (" Ana.Perez@Mail.com ", "ana.perez@mail.com"),
        ("JOSÉ-perez@mail.com", "josé-perez@mail.com"),
        ("a b@c.co", "ab@c.co"),
    ],
)
def test_email(valor: str, esperado: str) -> None:
    assert normalize_for_index(valor, "email") == esperado


@pytest.mark.parametrize(
    ("valor", "kind"), [(" . . ", "generic"), ("- -", "generic"), ("abc", "phone"), ("  ", "email")]
)
def test_valor_vacio(valor: str, kind: str) -> None:
    with pytest.raises(CryptoError) as excinfo:
        normalize_for_index(valor, kind)  # type: ignore[arg-type]
    assert excinfo.value.code == "empty_value"
    assert "valor vacío" in str(excinfo.value)
    assert valor.strip() == "" or valor not in str(excinfo.value)
