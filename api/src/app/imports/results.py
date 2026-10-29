"""Resultados de la importación de socios (privado de `app.imports`; S4B-D34).

Ningún campo lleva el valor de una celda: el documento va enmascarado y los motivos son frases
fijas (sin datos personales en reportes, salida ni registros).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RowResult:
    row: int
    document_masked: str | None
    result: str  # created | skipped_existing | rejected
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ImportResult:
    created: int = 0
    skipped_existing: int = 0
    rejected: int = 0
    consent_missing: int = 0
    notes_ignored: int = 0
    contacts_omitted: int = 0
    file_sha256: str = ""
    rows: list[RowResult] = field(default_factory=list)
