"""Tipos de validación compartidos por los schemas de los módulos (blueprint S2, decisión 5).

`EmailAddress` reemplaza a `EmailStr`: `email-validator` tiene licencia Unlicense (fuera de la
lista de `CLAUDE.md`) y arrastra `dnspython`. La validación es de forma, no de entrega:
recorta, pasa a minúsculas, tope de 254 caracteres y exige un solo `@`, nada de espacios y un
dominio con punto. El mensaje de error nunca repite el valor recibido.
"""

from __future__ import annotations

import re
from typing import Annotated, Final

from pydantic import AfterValidator, StringConstraints

EMAIL_MAX_LENGTH: Final[int] = 254
_FORMA_DE_CORREO: Final[re.Pattern[str]] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_email_shape(value: str) -> str:
    """Función pura: devuelve el correo tal cual o lanza `ValueError` sin el valor."""
    if not _FORMA_DE_CORREO.fullmatch(value):
        raise ValueError("El correo no tiene una forma válida.")
    return value


EmailAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=EMAIL_MAX_LENGTH),
    AfterValidator(check_email_shape),
]
