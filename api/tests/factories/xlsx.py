"""Fábricas de archivos `.xlsx` de la importación de socios (plan del Sprint 4B, sección 2, B1).

Todo se genera en la prueba (nunca se versiona un `.xlsx` con datos) y todo dato es ficticio.

- `fila_valida(n, **cambios)`: una fila de la plantilla Q17 (diez celdas, en el orden de
  `TEMPLATE_HEADER`) con documento `2000000 + n`; `cambios` pisa columnas por nombre.
- `make_members_xlsx(path, rows, *, header=TEMPLATE_HEADER)`: libro de una hoja con `openpyxl`;
  `header=None` no escribe cabecera (con `rows=[]` queda una hoja vacía).
- `make_xlsx_with_entry(path, nombre, data, *, compress)`: un libro válido al que se le agrega (o
  se le reemplaza) la entrada `nombre` del zip: `xl/vbaProject.bin`, `xl/externalLinks/x.xml`,
  `../fuera.xml`, `xl/sharedStrings.xml` de 11 MB declarados.
- `make_zip_bomb(path, uncompressed=60 MB)`: un libro válido con una entrada de ceros que ocupa
  pocos KB comprimida (razón de compresión enorme y más de 50 MB descomprimidos).
- `make_oversized_xlsx(path, size)`: un libro válido con una entrada SIN comprimir que deja el
  archivo en al menos `size` bytes (razón de compresión 1: aísla el tope de tamaño).
- `make_xlsx_xxe(path, secret_file)`: el nombre del primer socio es una entidad externa que apunta
  a `secret_file`; `make_xlsx_billion_laughs(path)`: entidades anidadas que se expanden a unos
  300 KB (acotado: basta para distinguir si el parser las expande o las rechaza).
"""

from __future__ import annotations

import base64
import os
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from openpyxl import Workbook

from app.imports.members_xlsx import TEMPLATE_HEADER

PLACEHOLDER: Final = "XXEPLACEHOLDER"
HOJA: Final = "xl/worksheets/sheet1.xml"  # openpyxl escribe cadenas en línea (`inlineStr`)
BOMBA_DESCOMPRIMIDA: Final = 60 * 1024 * 1024


def fila_valida(n: int, **cambios: object) -> list[object]:
    """Una fila de la plantilla con el socio ficticio `n` (documento de 7 dígitos)."""
    base: dict[str, object] = {
        "documento": str(2_000_000 + n),
        "nombres": f"Nombre{n}",
        "apellidos": f"Apellido{n}",
        "telefono": f"3005{n:06d}",
        "correo": f"socio{n}@ejemplo.com",
        "fecha_nacimiento": "1990-05-17",
        "sexo": "F",
        "contacto_emergencia_nombre": "Contacto Prueba",
        "contacto_emergencia_telefono": "3105550100",
        "notas": None,
    }
    desconocidas = set(cambios) - set(base)
    if desconocidas:
        raise KeyError(sorted(desconocidas))
    base.update(cambios)
    return [base[columna] for columna in TEMPLATE_HEADER]


def make_members_xlsx(
    path: Path,
    rows: Sequence[Sequence[object]],
    *,
    header: Sequence[object] | None = TEMPLATE_HEADER,
) -> Path:
    libro = Workbook()
    hoja: Any = libro.active
    if header is not None:
        hoja.append(list(header))
    for fila in rows:
        hoja.append(list(fila))
    path.parent.mkdir(parents=True, exist_ok=True)
    libro.save(path)
    return path


def _entradas(origen: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(origen) as zf:
        return {info.filename: zf.read(info) for info in zf.infolist()}


def _escribir(path: Path, entradas: dict[str, bytes], *, comprimir: dict[str, int]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, datos in entradas.items():
            tipo = comprimir.get(nombre, zipfile.ZIP_DEFLATED)
            zf.writestr(zipfile.ZipInfo(nombre), datos, compress_type=tipo)


def _libro_base(path: Path) -> dict[str, bytes]:
    base = make_members_xlsx(path.with_suffix(".base"), [fila_valida(1)])
    try:
        return _entradas(base)
    finally:
        base.unlink()


def make_xlsx_with_entry(
    path: Path, nombre: str, data: bytes = b"x", *, compress: int = zipfile.ZIP_DEFLATED
) -> Path:
    entradas = _libro_base(path)
    entradas[nombre] = data
    _escribir(path, entradas, comprimir={nombre: compress})
    return path


def make_zip_bomb(path: Path, uncompressed: int = BOMBA_DESCOMPRIMIDA) -> Path:
    return make_xlsx_with_entry(path, "docProps/relleno.bin", b"\0" * uncompressed)


def make_oversized_xlsx(path: Path, size: int) -> Path:
    relleno = "docProps/relleno.bin"
    sobra = 0
    for _ in range(3):
        entradas = _libro_base(path)
        entradas[relleno] = b"\0" * max(1, sobra or size // 2)
        _escribir(path, entradas, comprimir={relleno: zipfile.ZIP_STORED})
        actual = path.stat().st_size
        if actual >= size:
            return path
        sobra = len(entradas[relleno]) + (size - actual)
    raise AssertionError("no se pudo llegar al tamaño pedido")


def _con_doctype(path: Path, doctype: str, reemplazo: str) -> Path:
    clave = HOJA
    base = make_members_xlsx(
        path.with_suffix(".marca"), [fila_valida(1, nombres=PLACEHOLDER)], header=TEMPLATE_HEADER
    )
    try:
        entradas = _entradas(base)
    finally:
        base.unlink()
    xml = entradas[clave].decode("utf-8")
    assert PLACEHOLDER in xml, "el libro de partida debe llevar el nombre marcado"
    xml = xml.replace(PLACEHOLDER, reemplazo)
    cabeza, raiz, resto = xml.partition("<worksheet")
    entradas[clave] = f"{cabeza}{doctype}{raiz}{resto}".encode()
    _escribir(path, entradas, comprimir={})
    return path


def make_xlsx_xxe(path: Path, secret_file: Path) -> Path:
    doctype = f'<!DOCTYPE worksheet [<!ENTITY xxe SYSTEM "{secret_file.resolve().as_uri()}">]>'
    return _con_doctype(path, doctype, "&xxe;")


def make_xlsx_billion_laughs(path: Path, niveles: int = 5) -> Path:
    entidades = ['<!ENTITY lol0 "lol">']
    for i in range(1, niveles + 1):
        entidades.append(f'<!ENTITY lol{i} "{f"&lol{i - 1};" * 10}">')
    doctype = f"<!DOCTYPE worksheet [{''.join(entidades)}]>"
    return _con_doctype(path, doctype, f"&lol{niveles};")


def texto_incompresible(tamano: int) -> bytes:
    """`tamano` caracteres base64 de bytes aleatorios: comprime poco (razón < 2)."""
    crudo = os.urandom(tamano * 3 // 4 + 3)
    return base64.b64encode(crudo)[:tamano]
