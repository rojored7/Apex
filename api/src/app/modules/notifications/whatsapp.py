"""Enlace de WhatsApp (S5-B7, US-127; S5-D27, S5-D216, S5-D224). Privado: solo `service.py` lo
importa.

`build_link(phone, text)`: pura. Deja solo los dígitos del teléfono y solo acepta un celular
colombiano: 10 dígitos que empiezan por `3` (antepone `57`) o 12 que empiezan por `57`.
Cualquier otra forma (extranjero, truncado, `00...`) es `ValueError` sin repetir el número.
Arma `https://wa.me/57<digitos>?text=<texto>` con el texto pasado por `urllib.parse.quote` sin
caracteres seguros (todo lo que no sea alfanumérico o `-._~` va en porcentaje).
"""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

BASE_URL: Final = "https://wa.me/"
COUNTRY_CODE: Final = "57"
LOCAL_LENGTH: Final = 10
MOBILE_PREFIX: Final = "3"


def build_link(phone: str, text: str) -> str:
    """El enlace `wa.me`; `ValueError` si el teléfono no es un celular colombiano."""
    digitos = "".join(c for c in phone if c.isascii() and c.isdigit())
    if len(digitos) == LOCAL_LENGTH and digitos.startswith(MOBILE_PREFIX):
        digitos = COUNTRY_CODE + digitos
    elif not (
        len(digitos) == LOCAL_LENGTH + len(COUNTRY_CODE) and digitos.startswith(COUNTRY_CODE)
    ):
        raise ValueError("el teléfono no es un celular colombiano")
    return f"{BASE_URL}{digitos}?text={quote(text, safe='')}"
