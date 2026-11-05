"""Enlace de WhatsApp (S5-B7, US-127; S5-D27, S5-D216, S5-D224). Privado: solo `service.py` lo
importa.

`build_link(phone, text, *, country_code="57")`: pura. Deja solo los dígitos del teléfono. Con
`57` solo acepta un celular colombiano: 10 dígitos que empiezan por `3` (antepone `57`) o 12 que
empiezan por `57`; cualquier otra forma (extranjero, truncado, `00...`) es `ValueError` sin
repetir el número. Con otro indicativo (`settings.channels.whatsapp.country_code`, S5-D265c) acepta
de 8 a 15 dígitos y antepone el indicativo si el número no lo trae ya.
Arma `https://wa.me/<indicativo><digitos>?text=<texto>` con el texto pasado por
`urllib.parse.quote` sin caracteres seguros (lo que no sea alfanumérico o `-._~` va en porcentaje).
"""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

BASE_URL: Final = "https://wa.me/"
COUNTRY_CODE: Final = "57"
LOCAL_LENGTH: Final = 10
MOBILE_PREFIX: Final = "3"
MIN_DIGITS: Final = 8
MAX_DIGITS: Final = 15


def build_link(phone: str, text: str, *, country_code: str = COUNTRY_CODE) -> str:
    """El enlace `wa.me`; `ValueError` si el teléfono no es válido para `country_code`."""
    digitos = "".join(c for c in phone if c.isascii() and c.isdigit())
    if country_code == COUNTRY_CODE:
        digitos = _colombian(digitos)
    else:
        digitos = _foreign(digitos, country_code)
    return f"{BASE_URL}{digitos}?text={quote(text, safe='')}"


def _colombian(digitos: str) -> str:
    if len(digitos) == LOCAL_LENGTH and digitos.startswith(MOBILE_PREFIX):
        return COUNTRY_CODE + digitos
    if len(digitos) == LOCAL_LENGTH + len(COUNTRY_CODE) and digitos.startswith(COUNTRY_CODE):
        return digitos
    raise ValueError("el teléfono no es un celular colombiano")


def _foreign(digitos: str, country_code: str) -> str:
    """Otro indicativo (S5-D265c, S5-D270): el número guardado es SIEMPRE nacional (8 a 15
    dígitos, sin indicativo) y se antepone el indicativo sin detectar prefijos."""
    if not MIN_DIGITS <= len(digitos) <= MAX_DIGITS:
        raise ValueError("el teléfono no tiene entre 8 y 15 dígitos")
    return country_code + digitos
