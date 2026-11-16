"""Reglas puras de las medidas (S9-A1, US-178; S9-D3, S9-D4, S9-D32, S9-D36 L-1).

`encode_metric` y `decode_metric` convierten una medida al claro de ancho fijo que se cifra:
marca de campo (`w`, `h`, `f`, `n`) + dígitos. Así todos los blobs de un campo miden lo mismo y
un blob copiado a otra columna de la misma fila no se acepta (M-2). `notes` va como
`n` + 4 dígitos con los bytes UTF-8 del texto + texto + espacios hasta que el claro COMPLETO
(cabecera de 5 bytes incluida) mida un múltiplo de 128 bytes (L-1: oculta el largo). Los errores
nunca repiten el texto recibido ni encadenan la causa.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.modules.athletes.exceptions import MetricValidationError

METRIC_FIELDS: Final[tuple[str, ...]] = ("weight_g", "height_cm", "body_fat_pct", "notes")
FIELD_MARKS: Final[dict[str, str]] = {
    "weight_g": "w",
    "height_cm": "h",
    "body_fat_pct": "f",
    "notes": "n",
}
WEIGHT_MIN_G: Final = 20_000
WEIGHT_MAX_G: Final = 400_000
HEIGHT_MIN_CM: Final = 50
HEIGHT_MAX_CM: Final = 250
FAT_MIN_PCT: Final = 1
FAT_MAX_PCT: Final = 75
NOTES_MAX_CHARS: Final = 500
NOTES_BLOCK_BYTES: Final = 128
NOTES_HEADER_BYTES: Final = 5  # `n` + 4 dígitos
EARLIEST_MEASURED_ON: Final = date(2000, 1, 1)

# Campo -> (mínimo, máximo, dígitos del ancho fijo).
_NUMERIC: Final[dict[str, tuple[int, int, int]]] = {
    "weight_g": (WEIGHT_MIN_G, WEIGHT_MAX_G, 6),
    "height_cm": (HEIGHT_MIN_CM, HEIGHT_MAX_CM, 3),
    "body_fat_pct": (FAT_MIN_PCT, FAT_MAX_PCT, 2),
}
_OPAQUE: Final = "La medida guardada no es válida."


class MetricDecodeError(ValueError):
    """Un claro que no decodifica (marca ajena, largo o dígitos inválidos): mensaje fijo, opaco."""


def _opaque() -> MetricDecodeError:
    return MetricDecodeError(_OPAQUE)


def _check_field(field: str) -> None:
    if field not in FIELD_MARKS:
        raise ValueError("campo de medida desconocido")


def _out_of_range(field: str) -> MetricValidationError:
    return MetricValidationError(message="El valor está fuera del rango permitido.", field=field)


def _notes_padded_size(raw_len: int) -> int:
    total = NOTES_HEADER_BYTES + raw_len
    return -(-total // NOTES_BLOCK_BYTES) * NOTES_BLOCK_BYTES


def encode_metric(field: str, value: int | str) -> str:
    """Claro de ancho fijo con marca de campo; `MetricValidationError` si el valor no cabe."""
    _check_field(field)
    if field == "notes":
        if not isinstance(value, str) or not 1 <= len(value) <= NOTES_MAX_CHARS:
            raise _out_of_range(field)
        raw = value.encode("utf-8")
        cuerpo = f"n{len(raw):04d}{value}"
        return cuerpo + " " * (_notes_padded_size(len(raw)) - len(cuerpo.encode("utf-8")))
    minimo, maximo, digitos = _NUMERIC[field]
    if isinstance(value, bool) or not isinstance(value, int) or not minimo <= value <= maximo:
        raise _out_of_range(field)
    return f"{FIELD_MARKS[field]}{value:0{digitos}d}"


def _decode_notes(text: str) -> str:
    raw = text.encode("utf-8")
    if len(raw) < NOTES_HEADER_BYTES or raw[:1] != b"n" or len(raw) % NOTES_BLOCK_BYTES:
        raise _opaque()
    cuenta = raw[1:NOTES_HEADER_BYTES]
    if not (cuenta.isascii() and cuenta.isdigit()):
        raise _opaque()
    largo = int(cuenta)
    if (
        not 1 <= largo <= NOTES_MAX_CHARS * 4
        or NOTES_HEADER_BYTES + largo > len(raw)
        or len(raw) != _notes_padded_size(largo)
    ):
        raise _opaque()
    relleno = raw[NOTES_HEADER_BYTES + largo :]
    if relleno.strip(b" "):
        raise _opaque()
    try:
        return raw[NOTES_HEADER_BYTES : NOTES_HEADER_BYTES + largo].decode("utf-8")
    except UnicodeDecodeError:
        raise _opaque() from None


def decode_metric(field: str, text: str) -> int | str:
    """Inverso de `encode_metric`. Exige marca, largo exacto, dígitos ASCII y rango."""
    _check_field(field)
    if field == "notes":
        return _decode_notes(text)
    minimo, maximo, digitos = _NUMERIC[field]
    if len(text) != 1 + digitos or text[0] != FIELD_MARKS[field]:
        raise _opaque()
    cifras = text[1:]
    if not (cifras.isascii() and cifras.isdigit()):
        raise _opaque()
    valor = int(cifras)
    if not minimo <= valor <= maximo:
        raise _opaque()
    return valor


def validate_metric(
    *,
    measured_on: date,
    weight_g: int | None,
    height_cm: int | None,
    body_fat_pct: int | None,
    notes: str | None,
    today: date,
) -> None:
    """422 con `field` (sin repetir el valor). `today` es la fecha civil de Bogotá."""
    if not EARLIEST_MEASURED_ON <= measured_on <= today:
        raise MetricValidationError(
            message="La fecha de la medición no es válida.", field="measured_on"
        )
    valores: dict[str, int | None] = {
        "weight_g": weight_g,
        "height_cm": height_cm,
        "body_fat_pct": body_fat_pct,
    }
    for campo, valor in valores.items():
        if valor is not None:
            minimo, maximo, _ = _NUMERIC[campo]
            if not minimo <= valor <= maximo:
                raise _out_of_range(campo)
    if notes is not None and not 1 <= len(notes) <= NOTES_MAX_CHARS:
        raise _out_of_range("notes")
    if all(v is None for v in valores.values()):
        raise MetricValidationError(
            message="Registra al menos una medida: peso, estatura o grasa.", field="weight_g"
        )
