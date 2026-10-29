"""Tipos de validación compartidos por los schemas de los módulos (blueprint S2, decisión 5;
revisión del Sprint 2: N-2 y Python H2).

`EmailAddress` reemplaza a `EmailStr`: `email-validator` tiene licencia Unlicense (fuera de la
lista de `CLAUDE.md`) y arrastra `dnspython`. La validación es de forma, no de entrega:
recorta, pasa a minúsculas, tope de 254 caracteres y exige un solo `@`, nada de espacios, de
caracteres de control (`Cc`) ni de formato (`Cf`) y un dominio con punto. El mensaje de error
nunca repite el valor recibido.

Texto seguro (N-2): PostgreSQL rechaza el byte 0 como parámetro (asyncpg lanza y el handler lo
volvía 500, también en `POST /auth/login`, que es pública) y JSONB rechaza `\u0000`; además un
U+200B o un U+202E pasan el CHECK `btrim(x) <> ''` y se muestran en las listas (suplantación
visual). Por eso:
- `SafeText` (una línea: nombres, ciudad, dirección): NFC, recortado, sin `Cc` ni `Cf` y con al
  menos un carácter visible.
- `SafeMultilineText` (textos largos como la política de privacidad): NFC, admite tabulador y
  saltos de línea; rechaza los demás `Cc` y los controles bidireccionales (U+202A..U+202E,
  U+2066..U+2069); otros `Cf` (guion suave, ZWJ de un emoji) se aceptan porque llegan al pegar
  texto de un procesador y no rompen nada. Exige algo visible.

Rango de instantes de un filtro (S4A-B4; S4A-D46, S4A-D66; generaliza S3-D47 de pagos, que
`audit` no puede importar):
- `INSTANT_FLOOR` (2020-01-01T00:00Z) e `instant_ceiling(now)` (`now + 1 día`);
- `check_instant_range(start, end, *, now, field_start, field_end)`: `None` si el rango es válido;
  si no, `ValueError(<campo>)` (el único argumento es el nombre del campo, nunca el valor): sin
  zona horaria, antes del piso o después del techo da el campo de ese extremo; `start >= end` da
  `field_end`. Cada extremo puede ser `None`. Compara contra el piso y el techo antes de cualquier
  conversión, así un `0001-01-01T00:00:00+05:00` no rebasa el rango de `datetime`.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final

from pydantic import AfterValidator, StringConstraints

EMAIL_MAX_LENGTH: Final[int] = 254
_FORMA_DE_CORREO: Final[re.Pattern[str]] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CATEGORIAS_PROHIBIDAS: Final[frozenset[str]] = frozenset({"Cc", "Cf"})
_ESPACIOS_DE_TEXTO: Final[frozenset[str]] = frozenset({"\t", "\n", "\r"})
_BIDI: Final[frozenset[str]] = frozenset(
    chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
_MENSAJE_NO_PERMITIDOS: Final = "El texto tiene caracteres no permitidos."
_MENSAJE_VACIO: Final = "El texto no puede estar vacío."


def has_forbidden_chars(value: str) -> bool:
    """Pura: verdadero si `value` tiene un carácter de control (`Cc`) o de formato (`Cf`)."""
    return any(unicodedata.category(c) in _CATEGORIAS_PROHIBIDAS for c in value)


def check_visible_text(value: str) -> str:
    """Pura: NFC y recorte; `ValueError` (sin el valor) con `Cc`, `Cf` o sin nada visible."""
    texto = unicodedata.normalize("NFC", value).strip()
    if has_forbidden_chars(texto):
        raise ValueError(_MENSAJE_NO_PERMITIDOS)
    if not texto:
        raise ValueError(_MENSAJE_VACIO)
    return texto


def check_multiline_text(value: str) -> str:
    """Pura: como `check_visible_text`, pero admite tabulador y saltos y solo rechaza de `Cf`
    los controles bidireccionales."""
    texto = unicodedata.normalize("NFC", value)
    for caracter in texto:
        categoria = unicodedata.category(caracter)
        if categoria == "Cc" and caracter not in _ESPACIOS_DE_TEXTO:
            raise ValueError(_MENSAJE_NO_PERMITIDOS)
        if caracter in _BIDI:
            raise ValueError(_MENSAJE_NO_PERMITIDOS)
    if not texto.strip():
        raise ValueError(_MENSAJE_VACIO)
    return texto


def check_email_shape(value: str) -> str:
    """Función pura: devuelve el correo tal cual o lanza `ValueError` sin el valor."""
    if has_forbidden_chars(value) or not _FORMA_DE_CORREO.fullmatch(value):
        raise ValueError("El correo no tiene una forma válida.")
    return value


SafeText = Annotated[str, AfterValidator(check_visible_text)]
SafeMultilineText = Annotated[str, AfterValidator(check_multiline_text)]

EmailAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=EMAIL_MAX_LENGTH),
    AfterValidator(check_email_shape),
]


# Rango de instantes de un filtro (S4A-B4; S4A-D46, S4A-D66) ---------------------------------

INSTANT_FLOOR: Final = datetime(2020, 1, 1, tzinfo=UTC)
INSTANT_CEILING_TOLERANCE: Final = timedelta(days=1)


def instant_ceiling(now: datetime) -> datetime:
    """Techo de un filtro de instantes: `now + 1 día` (S4A-D46)."""
    return now + INSTANT_CEILING_TOLERANCE


def _instant_in_range(value: datetime, ceiling: datetime) -> bool:
    """Con zona y dentro de `[INSTANT_FLOOR, ceiling]`. Comparar dos `datetime` con zona no
    convierte a UTC, así que un extremo como el año 1 no rebasa el rango de `datetime`."""
    if value.tzinfo is None or value.utcoffset() is None:
        return False
    return INSTANT_FLOOR <= value <= ceiling


def check_instant_range(
    start: datetime | None,
    end: datetime | None,
    *,
    now: datetime,
    field_start: str,
    field_end: str,
) -> None:
    """`None` si `[start, end)` es válido; si no, `ValueError(<campo>)` (ver el docstring)."""
    ceiling = instant_ceiling(now)
    if start is not None and not _instant_in_range(start, ceiling):
        raise ValueError(field_start)
    if end is not None and not _instant_in_range(end, ceiling):
        raise ValueError(field_end)
    if start is not None and end is not None and start >= end:
        raise ValueError(field_end)
