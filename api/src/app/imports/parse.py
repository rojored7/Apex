"""Cabecera, fila y enmascarado de la plantilla de socios (privado de `app.imports`; Q17, S4B-D35).

Funciones puras. Contrato de salida: ningún `RowError.reason` repite el valor de la celda.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from pydantic import ValidationError

from app.imports.limits import MAX_CELL_CHARS
from app.modules.members.schemas import EmergencyContactIn, MemberCreate

TEMPLATE_HEADER: Final = (
    "documento",
    "nombres",
    "apellidos",
    "telefono",
    "correo",
    "fecha_nacimiento",
    "sexo",
    "contacto_emergencia_nombre",
    "contacto_emergencia_telefono",
    "notas",
)
COLUMNS: Final = {nombre: indice for indice, nombre in enumerate(TEMPLATE_HEADER)}
FORMULA_STARTS: Final = ("=", "+", "-", "@")
SEXES: Final = frozenset({"f", "m", "x"})
_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_DOCUMENT_NOISE: Final = re.compile(r"[\d.\s-]+")
_FIELD_NAMES: Final = {
    "first_name": "nombres",
    "last_name": "apellidos",
    "document": "documento",
    "phone": "telefono",
    "email": "correo",
    "birth_date": "fecha_nacimiento",
    "sex": "sexo",
    "emergency_contact": "contacto de emergencia",
}


class HeaderError(ValueError):
    """La cabecera no es exactamente la de Q17."""


@dataclass(frozen=True, slots=True)
class RowError:
    """Fila rechazada: `reason` es una frase fija (se devuelve, no se lanza, desde `parse_*`)."""

    row: int
    reason: str


class _Reject(Exception):
    """Interna: corta el análisis de una celda con su frase fija."""


def validate_header(cells: Sequence[object]) -> None:
    """Exige las diez columnas de Q17, en ese orden y con ese texto; si no, `HeaderError`."""
    if tuple(cells) != TEMPLATE_HEADER:
        raise HeaderError("la cabecera no coincide con la plantilla de importar socios")


def mask_document(document: str) -> str:
    """`1020304` -> `•••304`; un documento corto (menos de 7) no deja ningún dígito a la vista."""
    return f"•••{document[-3:]}" if len(document) >= 7 else "•••"


def _text(valor: object) -> str | None:
    """Celda de texto recortada; vacía -> `None`; otra cosa que texto -> `_Reject`."""
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise _Reject("valor con formato no permitido")
    return _no_formula(valor.strip()) or None


def _no_formula(texto: str) -> str:
    """Una celda de texto no puede empezar por `=`, `+`, `-` o `@` (inyección de fórmulas en
    exportaciones futuras; revisión de seguridad de B1): vale para todo campo de texto."""
    if texto.startswith(FORMULA_STARTS):
        raise _Reject("un valor no puede empezar por = + - o @")
    return texto


def _digits_cell(valor: object) -> str | None:
    """Documento o teléfono: texto, entero o decimal sin fracción (`1020304.0`)."""
    if isinstance(valor, bool):
        raise _Reject("valor con formato no permitido")
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if not valor.is_integer():
            raise _Reject("valor numérico no entero")
        return str(int(valor))
    return _text(valor)


def clean_document(valor: object) -> str | None:
    """`1020304.0`, `1.020.304`, `1 020 304` y `1020-304` -> `1020304`; un documento con letras
    se conserva (recortado)."""
    texto = _digits_cell(valor)
    if texto is not None and _DOCUMENT_NOISE.fullmatch(texto):
        return re.sub(r"[.\s-]", "", texto)
    return texto


def _birth_date(valor: object) -> date | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and _DATE.fullmatch(valor.strip()):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            pass
    raise _Reject("fecha de nacimiento inválida (use AAAA-MM-DD)")


def _sex(valor: object) -> str | None:
    texto = _text(valor)
    if texto is None:
        return None
    if texto.lower() not in SEXES:
        raise _Reject("sexo inválido (use F, M o X)")
    return texto.lower()


def _person_name(valor: object, campo: str) -> str:
    texto = _text(valor)
    if texto is None:
        raise _Reject(f"{campo} es obligatorio")
    return texto


def _check_cell_sizes(cells: Sequence[object]) -> None:
    if any(isinstance(c, str) and len(c) > MAX_CELL_CHARS for c in cells):
        raise _Reject(f"una celda excede {MAX_CELL_CHARS} caracteres")


def padded(cells: Sequence[object]) -> list[object]:
    """Las diez celdas de la fila (las que falten, vacías)."""
    return [*cells[: len(TEMPLATE_HEADER)], *[None] * (len(TEMPLATE_HEADER) - len(cells))]


def contact_cells(cells: Sequence[object]) -> tuple[str | None, str | None]:
    fila = padded(cells)
    nombre = _text(fila[COLUMNS["contacto_emergencia_nombre"]])
    telefono = _digits_cell(fila[COLUMNS["contacto_emergencia_telefono"]])
    return nombre, telefono


def contact_omitted(cells: Sequence[object]) -> bool:
    """Hay solo uno de los dos datos del contacto de emergencia (S4B-D35)."""
    nombre, telefono = contact_cells(cells)
    return (nombre is None) != (telefono is None)


def notes_present(cells: Sequence[object]) -> bool:
    """La columna `notas` trae algo (se ignora: `MemberCreate` no la guarda)."""
    nota = padded(cells)[COLUMNS["notas"]]
    return nota is not None and bool(str(nota).strip())


def is_blank_row(cells: Sequence[object]) -> bool:
    return all(c is None or (isinstance(c, str) and not c.strip()) for c in cells)


def _emergency_contact(cells: Sequence[object]) -> EmergencyContactIn | None:
    nombre, telefono = contact_cells(cells)
    if nombre is None or telefono is None:
        return None
    return EmergencyContactIn(name=nombre, phone=telefono)


def _build(fila: list[object]) -> MemberCreate:
    columna = COLUMNS
    documento = clean_document(fila[columna["documento"]])
    if documento is None:
        raise _Reject("documento es obligatorio")
    return MemberCreate(
        first_name=_person_name(fila[columna["nombres"]], "nombres"),
        last_name=_person_name(fila[columna["apellidos"]], "apellidos"),
        document=documento,
        phone=_digits_cell(fila[columna["telefono"]]),
        email=_text(fila[columna["correo"]]),
        birth_date=_birth_date(fila[columna["fecha_nacimiento"]]),
        sex=_sex(fila[columna["sexo"]]),
        emergency_contact=_emergency_contact(fila),
        data_consent=False,  # Q16, S4B-D77: la autorización no se presume
    )


def _validation_reason(error: ValidationError) -> str:
    """El campo que falló, nunca el valor."""
    ubicacion = error.errors(include_input=False, include_url=False)[0]["loc"]
    campo = str(ubicacion[0]) if ubicacion else ""
    return f"{_FIELD_NAMES.get(campo, 'fila')} inválido"


def parse_member_row(row_number: int, cells: Sequence[object]) -> MemberCreate | RowError:
    """La fila de la plantilla como `MemberCreate` (sin autorización de datos) o su rechazo."""
    try:
        _check_cell_sizes(cells)
        return _build(padded(cells))
    except _Reject as rechazo:
        return RowError(row_number, str(rechazo))
    except ValidationError as error:
        return RowError(row_number, _validation_reason(error))


def masked_document_of(cells: Sequence[object]) -> str | None:
    """El documento de la fila enmascarado, o `None` si la celda no se puede leer (para el
    reporte de una fila rechazada)."""
    try:
        documento = clean_document(padded(cells)[COLUMNS["documento"]])
    except _Reject:
        return None
    return None if documento is None else mask_document(documento)
