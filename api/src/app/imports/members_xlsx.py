"""Lectura e importación de la plantilla de socios (S4B-D34, D35, D64; Q17).

Fachada del paquete: reexporta lo público de los privados (`limits`, `parse`, `results`,
`report`) y es quien lee el libro con `openpyxl` (protegido por `defusedxml`, sin `lxml`).
Contrato de salida: ningún mensaje ni `RowError.reason` repite un valor de la celda.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.xml import DEFUSEDXML, LXML  # type: ignore[import-untyped]

from app.cli_base import unit_of_work
from app.core.clock import current_clock
from app.core.config import Settings
from app.core.crypto.digest import sha256_hex
from app.core.crypto.normalize import normalize_for_index
from app.core.errors import DomainError
from app.imports.limits import (
    MAX_CELL_CHARS,
    MAX_COMPRESSION_RATIO,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    MAX_ROWS,
    MAX_SHARED_STRINGS_BYTES,
    MAX_UNCOMPRESSED_BYTES,
    LimitError,
    check_limits,
    read_input,
    resolve_input,
)
from app.imports.parse import (
    TEMPLATE_HEADER,
    HeaderError,
    RowError,
    contact_omitted,
    is_blank_row,
    mask_document,
    masked_document_of,
    notes_present,
    parse_member_row,
    validate_header,
)
from app.imports.persist import create_member, document_exists, write_summary
from app.imports.report import report_path, write_report
from app.imports.results import ImportResult, RowResult
from app.modules.members import service as members_service
from app.modules.members.schemas import MemberCreate

__all__ = [
    "MAX_CELL_CHARS",
    "MAX_COMPRESSION_RATIO",
    "MAX_ENTRIES",
    "MAX_FILE_BYTES",
    "MAX_ROWS",
    "MAX_SHARED_STRINGS_BYTES",
    "MAX_UNCOMPRESSED_BYTES",
    "TEMPLATE_HEADER",
    "HeaderError",
    "ImportResult",
    "LimitError",
    "RowError",
    "RowResult",
    "check_limits",
    "import_members",
    "mask_document",
    "parse_member_row",
    "read_rows",
    "resolve_input",
    "validate_header",
]

logger = logging.getLogger("app.imports")
DUPLICATE_IN_FILE = "documento repetido en el archivo"
ALREADY_EXISTS = "el socio ya existe"
INVALID_DATA = "datos del socio no válidos"
UNREADABLE = "el archivo no se pudo leer como libro de Excel"


def read_rows(datos: bytes) -> list[tuple[object, ...]]:
    """Filas de la primera hoja, hasta `MAX_ROWS + 2`, con `max_col=len(TEMPLATE_HEADER)`.

    Cualquier fallo del lector (XML con entidades que `defusedxml` rechaza, libro roto) es un
    `LimitError` con mensaje fijo: el texto del error original puede traer contenido del archivo.
    """
    if not DEFUSEDXML or LXML:
        raise LimitError("openpyxl debe correr con defusedxml y sin lxml")
    try:
        libro = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
        try:
            hoja = libro.worksheets[0]
            filas = hoja.iter_rows(
                min_row=1, max_row=MAX_ROWS + 2, max_col=len(TEMPLATE_HEADER), values_only=True
            )
            return [tuple(fila) for fila in filas]
        finally:
            libro.close()
    except LimitError:
        raise
    except Exception:
        raise LimitError(UNREADABLE) from None


@dataclass(slots=True)
class _Tally:
    """Conteos y filas de la corrida."""

    rows: list[RowResult] = field(default_factory=list)
    created: int = 0
    skipped: int = 0
    rejected: int = 0
    consent_missing: int = 0
    notes_ignored: int = 0
    contacts_omitted: int = 0

    def reject(self, number: int, masked: str | None, reason: str) -> None:
        self.rejected += 1
        self.rows.append(RowResult(number, masked, "rejected", reason))

    def skip(self, number: int, masked: str, reason: str) -> None:
        self.skipped += 1
        self.rows.append(RowResult(number, masked, "skipped_existing", reason))

    def create(self, number: int, masked: str, cells: Sequence[object]) -> None:
        omitido, nota = contact_omitted(cells), notes_present(cells)
        self.created += 1
        self.consent_missing += 1  # Q16, S4B-D77: ninguno trae autorización
        self.contacts_omitted += int(omitido)
        self.notes_ignored += int(nota)
        motivos = [
            m for m, hay in (("contacto omitido", omitido), ("notas ignoradas", nota)) if hay
        ]
        self.rows.append(RowResult(number, masked, "created", "; ".join(motivos) or None))


@dataclass(frozen=True, slots=True)
class _Prepared:
    """Lo leído y validado ANTES de escribir nada."""

    rows: list[tuple[int, tuple[object, ...]]]
    sha256: str
    report: Path | None


def _prepare(settings: Settings, path: Path, report: str | None) -> _Prepared:
    destino = report_path(report, settings.IMPORT_DIR) if report is not None else None
    datos = read_input(resolve_input(path, settings.IMPORT_DIR))
    check_limits(datos, path.name)
    filas = read_rows(datos)
    if not filas:
        raise LimitError("la hoja está vacía")
    validate_header(filas[0])
    cuerpo = [(n, f) for n, f in enumerate(filas[1:], start=2) if not is_blank_row(f)]
    if len(cuerpo) > MAX_ROWS:
        raise LimitError(f"el archivo tiene más de {MAX_ROWS} filas de datos")
    return _Prepared(cuerpo, sha256_hex(datos), destino)


def _domain_error(data: MemberCreate, today: date) -> str | None:
    """Reglas del alta que el esquema no expresa (fecha futura, documento vacío...)."""
    try:
        members_service.validate_member_input(data, today)
    except DomainError:
        return INVALID_DATA
    return None


async def _handle_row(
    session_factory: Any,
    number: int,
    cells: tuple[object, ...],
    seen: set[str],
    tally: _Tally,
    *,
    today: date,
    dry_run: bool,
) -> None:
    parsed = parse_member_row(number, cells)
    if isinstance(parsed, RowError):
        tally.reject(number, masked_document_of(cells), parsed.reason)
        return
    masked = mask_document(parsed.document)
    if (invalido := _domain_error(parsed, today)) is not None:
        tally.reject(number, masked, invalido)
        return
    llave = normalize_for_index(parsed.document, "generic")
    if llave in seen:
        tally.skip(number, masked, DUPLICATE_IN_FILE)
        return
    seen.add(llave)
    if await document_exists(session_factory, parsed.document):
        tally.skip(number, masked, ALREADY_EXISTS)
    elif dry_run or await create_member(session_factory, parsed):
        tally.create(number, masked, cells)
    else:
        tally.skip(number, masked, ALREADY_EXISTS)


def _result_of(tally: _Tally, sha256: str) -> ImportResult:
    return ImportResult(
        created=tally.created,
        skipped_existing=tally.skipped,
        rejected=tally.rejected,
        consent_missing=tally.consent_missing,
        notes_ignored=tally.notes_ignored,
        contacts_omitted=tally.contacts_omitted,
        file_sha256=sha256,
        rows=tally.rows,
    )


async def _close_run(
    fabrica: Any,
    tally: _Tally,
    preparado: _Prepared,
    actor_id: UUID,
    dry_run: bool,
    completo: bool,
) -> ImportResult:
    """Resumen de auditoría (S4B-D36: solo si hubo altas) y reporte, también tras un fallo."""
    resultado = _result_of(tally, preparado.sha256)
    with unit_of_work(actor_id):
        if tally.created and not dry_run:
            await write_summary(fabrica, resultado, len(preparado.rows), partial=not completo)
    if preparado.report is not None:
        write_report(preparado.report, resultado.rows, current_clock().now_utc())
    return resultado


async def import_members(
    settings: Settings,
    path: Path,
    actor_id: UUID,
    *,
    dry_run: bool,
    report: str | None,
) -> ImportResult:
    """Importa la plantilla (idempotente por documento). Valida archivo, límites, cabecera y
    reporte ANTES de escribir; un alta por transacción; resumen de auditoría al final."""
    from app.core import db

    preparado = _prepare(settings, path, report)
    fabrica = db.get_sessionmaker()
    hoy = current_clock().today_bogota()
    tally, vistos = _Tally(), set[str]()
    completo = False
    try:
        with unit_of_work(actor_id):
            for numero, celdas in preparado.rows:
                await _handle_row(
                    fabrica, numero, celdas, vistos, tally, today=hoy, dry_run=dry_run
                )
            completo = True
    finally:
        # Revisión de seguridad de B1 (MEDIUM): si una alta falla a mitad, lo ya confirmado
        # queda registrado (resumen con `partial=true`) y el reporte lista hasta donde llegó.
        resultado = await _close_run(fabrica, tally, preparado, actor_id, dry_run, completo)
    logger.info(
        "importación de socios terminada",
        extra={"rows_created": tally.created, "rows_rejected": tally.rejected, "dry_run": dry_run},
    )
    return resultado
