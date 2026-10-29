"""Límites y confinamiento del archivo de importación (privado de `app.imports`; S4B-D34, D64).

Orden de las comprobaciones (M-6): ruta dentro de `IMPORT_DIR` y archivo regular sin enlaces;
tamaño (≤ 10 MB); estructura del zip (entradas, bytes descomprimidos, razón de compresión,
rutas, partes peligrosas, `sharedStrings.xml`); extensión `.xlsx` exacta. Los mensajes son fijos:
nunca llevan una ruta ni un valor del archivo.
"""

from __future__ import annotations

import io
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

MAX_ROWS: Final = 5000
MAX_FILE_BYTES: Final = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES: Final = 50 * 1024 * 1024
MAX_ENTRIES: Final = 200
MAX_COMPRESSION_RATIO: Final = 100
MAX_SHARED_STRINGS_BYTES: Final = 10 * 1024 * 1024
MAX_CELL_CHARS: Final = 200
FORBIDDEN_PARTS: Final = (
    "xl/vbaProject.bin",
    "xl/externalLinks/",
    "xl/embeddings/",
    "xl/activeX/",
    "xl/macrosheets/",
)
SHARED_STRINGS: Final = "xl/sharedStrings.xml"
EXTENSION: Final = ".xlsx"


class LimitError(ValueError):
    """El archivo excede un límite o no es un `.xlsx` aceptable (salida 2)."""


def resolve_input(path: Path, import_dir: Path) -> int:
    """Descriptor de un archivo regular dentro de `import_dir` (sin enlaces); `LimitError` si no.

    Una ruta relativa se lee desde `import_dir`. `Path.resolve(strict=True)` sigue los enlaces:
    uno que sale de `import_dir` no pasa el prefijo, y el propio argumento no puede ser un enlace.
    """
    try:
        base = import_dir.resolve(strict=True)
        candidato = path if path.is_absolute() else base / path
        if candidato.is_symlink():
            raise LimitError("el archivo no puede ser un enlace simbólico")
        real = candidato.resolve(strict=True)
    except OSError:
        raise LimitError("el archivo no existe o no se puede leer") from None
    if not real.is_relative_to(base):
        raise LimitError("el archivo debe estar dentro de IMPORT_DIR")
    banderas = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(real, banderas | getattr(os, "O_BINARY", 0))
    except OSError:
        raise LimitError("el archivo no existe o no se puede leer") from None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise LimitError("el archivo debe ser un archivo regular")
    return fd


def read_input(fd: int) -> bytes:
    """Lee el archivo UNA vez y cierra el descriptor; `LimitError` si pasa de 10 MB."""
    with os.fdopen(fd, "rb") as archivo:
        if os.fstat(archivo.fileno()).st_size > MAX_FILE_BYTES:
            raise LimitError("el archivo excede el tamaño máximo de 10 MB")
        datos = archivo.read(MAX_FILE_BYTES + 1)
    if len(datos) > MAX_FILE_BYTES:
        raise LimitError("el archivo excede el tamaño máximo de 10 MB")
    return datos


def _name_error(nombre: str) -> str | None:
    ruta = PurePosixPath(nombre.replace("\\", "/"))
    if ruta.is_absolute() or ".." in ruta.parts or (len(nombre) > 1 and nombre[1] == ":"):
        return "el libro trae rutas internas no permitidas"
    if nombre.startswith(FORBIDDEN_PARTS):
        return "el libro trae macros, vínculos externos u objetos incrustados"
    return None


def _entry_error(info: zipfile.ZipInfo) -> str | None:
    if (rechazo := _name_error(info.filename)) is not None:
        return rechazo
    if info.filename == SHARED_STRINGS and info.file_size > MAX_SHARED_STRINGS_BYTES:
        return "las cadenas compartidas del libro exceden 10 MB"
    if info.file_size and info.compress_size == 0:
        return "el libro tiene una razón de compresión no permitida"
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        return "el libro tiene una razón de compresión no permitida"
    return None


def check_limits(datos: bytes, filename: str) -> None:
    """Estructura del zip y extensión (el tamaño ya lo dio `read_input`); `LimitError` si falla."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as libro:
            entradas = libro.infolist()
    except zipfile.BadZipFile:
        raise LimitError("el archivo no es un libro .xlsx válido") from None
    if len(entradas) > MAX_ENTRIES:
        raise LimitError("el libro tiene demasiadas entradas")
    if sum(info.file_size for info in entradas) > MAX_UNCOMPRESSED_BYTES:
        raise LimitError("el libro descomprimido excede 50 MB")
    for info in entradas:
        if (rechazo := _entry_error(info)) is not None:
            raise LimitError(rechazo)
    if Path(filename).suffix.lower() != EXTENSION:
        raise LimitError("solo se aceptan archivos .xlsx")
