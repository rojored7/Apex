"""Escritor de PDF propio (S5-D65, S5-D61, M-11): una página A4, Courier sin incrustar.

`render_text_pdf(lines, *, title) -> bytes` arma un PDF 1.4 de una sola página con la biblioteca
estándar. Es el único sitio que escribe PDF (no hay `reportlab` ni `fpdf2`; licencias en
`CLAUDE.md`). Solo dibuja texto: no hay imágenes, enlaces, formularios ni scripts.

Garantías (M-11, cada una la fija `tests/core/test_pdf.py`):
- Texto no confiable: TODA cadena se escribe en hexadecimal (`<...> Tj` y el título de `/Info`),
  así ningún carácter del usuario puede cerrar una cadena, abrir un objeto ni inyectar una clave
  del lenguaje PDF; en el archivo no hay paréntesis ni barras invertidas.
- Codificación: `WinAnsiEncoding` (cp1252). Lo que no cabe (fuera de cp1252, controles, NUL, tab,
  U+202E, emoji) sale como `?`, también en el título.
- Estructura: sin `/Filter` (flujo sin comprimir, `/Length` es el largo real), tabla `xref` con los
  desplazamientos medidos sobre los bytes ya escritos y `startxref`. Ninguna de las claves activas
  (`/JavaScript`, `/JS`, `/OpenAction`, `/AA`, `/URI`, `/Launch`, `/Annots`, `/EmbeddedFile`).
- Tope: más de `MAX_PDF_BYTES` es `ValueError` (la salida es de tamaño acotado).

Posiciones en milímetros desde la esquina inferior izquierda; el contenido las pasa a puntos
(`mm * 72 / 25.4`) y coloca cada línea con `Tm` (matriz de texto absoluta).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

MAX_PDF_BYTES: Final = 100_000

PAGE_WIDTH_PT: Final = 595.28
PAGE_HEIGHT_PT: Final = 841.89
POINTS_PER_MM: Final = 72 / 25.4
_REPLACEMENT: Final = "?"
_HEADER: Final = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
_CONTROL_LIMIT: Final = 0x20
_DEL: Final = 0x7F


@dataclass(frozen=True, slots=True)
class PdfLine:
    """Una línea de texto: posición en milímetros desde la esquina inferior izquierda."""

    text: str
    x_mm: float
    y_mm: float
    size: float
    bold: bool = False


def _winansi_char(char: str) -> str:
    """El carácter si cp1252 lo representa y no es un control; si no, `?`."""
    try:
        codigo = char.encode("cp1252")[0]
    except UnicodeEncodeError:
        return _REPLACEMENT
    if codigo < _CONTROL_LIMIT or codigo == _DEL:
        return _REPLACEMENT
    return char


def sanitize(text: str) -> str:
    """El texto con cada carácter no representable en WinAnsi cambiado por `?`."""
    return "".join(_winansi_char(c) for c in text)


def _hex_content(text: str) -> str:
    """Cadena PDF hexadecimal en WinAnsi (un byte por carácter)."""
    return "<" + sanitize(text).encode("cp1252").hex().upper() + ">"


def _hex_title(text: str) -> str:
    """Cadena PDF hexadecimal en UTF-16BE con marca de orden (texto de `/Info`)."""
    return "<FEFF" + sanitize(text).encode("utf-16-be").hex().upper() + ">"


def _num(value: float) -> str:
    """Número PDF con hasta dos decimales; `ValueError` si no es finito."""
    if not math.isfinite(value):
        raise ValueError("pdf: número no finito")
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _line_ops(line: PdfLine) -> str:
    """Operadores de una línea: fuente y tamaño, matriz de texto absoluta y la cadena."""
    if not line.size > 0:
        raise ValueError("pdf: el tamaño de la fuente debe ser positivo")
    fuente = "F2" if line.bold else "F1"
    x = _num(line.x_mm * POINTS_PER_MM)
    y = _num(line.y_mm * POINTS_PER_MM)
    return f"BT /{fuente} {_num(line.size)} Tf 1 0 0 1 {x} {y} Tm {_hex_content(line.text)} Tj ET\n"


def _objects(lines: Sequence[PdfLine], title: str) -> list[bytes]:
    """Los 7 objetos en orden (1 a 7): catálogo, páginas, página, contenido, dos fuentes, info."""
    flujo = "".join(_line_ops(linea) for linea in lines).encode("ascii")
    ancho, alto = _num(PAGE_WIDTH_PT), _num(PAGE_HEIGHT_PT)
    fuente = "<< /Type /Font /Subtype /Type1 /BaseFont /{} /Encoding /WinAnsiEncoding >>"
    return [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ancho} {alto}] "
            "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
        ).encode("ascii"),
        b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"endstream",
        fuente.format("Courier").encode("ascii"),
        fuente.format("Courier-Bold").encode("ascii"),
        f"<< /Title {_hex_title(title)} >>".encode("ascii"),
    ]


def _assemble(objects: Sequence[bytes]) -> bytes:
    """Cabecera, objetos numerados, `xref` con desplazamientos reales, `trailer` y `startxref`."""
    salida = bytearray(_HEADER)
    desplazamientos: list[int] = []
    for numero, cuerpo in enumerate(objects, start=1):
        desplazamientos.append(len(salida))
        salida += b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    total = len(objects) + 1
    salida += b"xref\n0 %d\n" % total + b"0000000000 65535 f \n"
    for desplazamiento in desplazamientos:
        salida += b"%010d 00000 n \n" % desplazamiento
    salida += b"trailer\n<< /Size %d /Root 1 0 R /Info 7 0 R >>\n" % total
    salida += b"startxref\n%d\n%%%%EOF\n" % inicio_xref
    return bytes(salida)


def render_text_pdf(lines: Sequence[PdfLine], *, title: str) -> bytes:
    """El PDF de una página con `lines`; `ValueError` si supera `MAX_PDF_BYTES`."""
    datos = _assemble(_objects(lines, title))
    if len(datos) > MAX_PDF_BYTES:
        raise ValueError(f"pdf: {len(datos)} bytes superan el tope de {MAX_PDF_BYTES}")
    return datos


__all__ = ["MAX_PDF_BYTES", "PdfLine", "render_text_pdf", "sanitize"]
