"""Reporte CSV de la importación (S4B-D34, D64): documento enmascarado, sin otros datos."""

from __future__ import annotations

import csv
import io
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from app.imports.limits import LimitError
from app.imports.results import RowResult

BOM = "﻿"
HEADER = ("fila", "documento", "resultado", "motivo")


def report_path(name: str, import_dir: Path) -> Path:
    """Ruta de `name` dentro de `import_dir`; `LimitError` si es otra cosa que un nombre o si ya
    existe (o es un enlace): el reporte nunca pisa nada."""
    simple = (
        name
        and name not in (".", "..")
        and "/" not in name
        and "\\" not in name
        and "\0" not in name
        and ":" not in name
        and Path(name).name == name
    )
    if not simple:
        raise LimitError("--report debe ser solo un nombre de archivo, sin carpetas")
    try:
        destino = import_dir.resolve(strict=True) / name
    except OSError:
        raise LimitError("IMPORT_DIR no existe") from None
    if os.path.lexists(destino):
        raise LimitError("el reporte ya existe; elija otro nombre")
    return destino


def render_report(results: Sequence[RowResult]) -> bytes:
    """El CSV `;` con BOM UTF-8: `fila;documento;resultado;motivo`."""
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(HEADER)
    for fila in results:
        escritor.writerow([fila.row, fila.document_masked or "", fila.result, fila.reason or ""])
    return (BOM + salida.getvalue()).encode("utf-8")


def write_report(path: Path, results: Sequence[RowResult], now: datetime) -> None:
    """Crea `path` con `O_EXCL | O_NOFOLLOW` y modo 0o600; `now` no entra en el contenido (el
    reporte de `--dry-run` y el real son idénticos byte a byte)."""
    del now
    banderas = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    banderas |= getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, banderas, 0o600)
    except OSError:
        raise LimitError("no se pudo crear el reporte; elija otro nombre") from None
    with os.fdopen(fd, "wb") as archivo:
        archivo.write(render_report(results))
