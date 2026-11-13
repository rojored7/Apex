"""Reglas puras de adjuntos (S6-C1; S6-D22, S6-D59, S6-D84): sin base, disco ni red."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.modules.attachments.exceptions import FileTooLarge, UnsupportedType

ATTACHMENT_MAX_BYTES: Final = 5_242_880
ATTACHMENT_READ_LIMIT: Final = 5_242_881
ATTACHMENT_UPLOAD_TIMEOUT_S: Final = 30.0

JPEG: Final = "image/jpeg"
PNG: Final = "image/png"
PDF: Final = "application/pdf"

_MAGIC: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\xff\xd8\xff", JPEG),
    (b"\x89PNG\r\n\x1a\n", PNG),
    (b"%PDF-", PDF),
)
_IMAGES: Final = frozenset({JPEG, PNG})
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "photo": _IMAGES,
    "consent": frozenset({JPEG, PNG, PDF}),
    "other": frozenset({JPEG, PNG, PDF}),
}
_SENSITIVE: Final = frozenset({"consent", "other"})


@dataclass(frozen=True)
class OrphanReport:
    """Ids de filas sin objeto, nombres (hex) de objetos sin fila e ids de sensibles con `key_id`
    distinto del blob, ordenados."""

    rows_without_object: tuple[UUID, ...]
    objects_without_row: tuple[str, ...]
    key_mismatch: tuple[UUID, ...] = ()  # sensibles cuyo `key_id` difiere del blob (V9 M1)


def detect_mime(head: bytes) -> str | None:
    """El tipo lo deciden los bytes mágicos; ni la extensión ni el `Content-Type` cuentan."""
    for firma, mime in _MAGIC:
        if head.startswith(firma):
            return mime
    return None


def validate_upload(size_bytes: int, mime: str, kind: str) -> None:
    if size_bytes > ATTACHMENT_MAX_BYTES:
        raise FileTooLarge
    if size_bytes < 1:
        raise UnsupportedType
    permitidos = _ALLOWED.get(kind)
    if permitidos is None:
        raise ValueError(f"kind desconocido: {kind!r}")
    if mime not in permitidos:
        raise UnsupportedType


def kind_is_sensitive(kind: str) -> bool:
    if kind not in _ALLOWED:
        raise ValueError(f"kind desconocido: {kind!r}")
    return kind in _SENSITIVE


def can_download(role: str, sensitive: bool) -> bool:
    """Descarga (S6-C4, M-6): el admin baja todo; el coach solo lo no sensible (la foto)."""
    return role == "admin" or (role == "coach" and not sensitive)


_EXTENSION: Final = {JPEG: "jpg", PNG: "png", PDF: "pdf"}


def download_filename(attachment_id: UUID, mime: str) -> str:
    """`adjunto-<8 hex>.<ext>`: solo un prefijo del id, nunca `filename_random` ni el id entero."""
    return f"adjunto-{attachment_id.hex[:8]}.{_EXTENSION[mime]}"


def find_orphans(row_keys: Mapping[UUID, str], stored_keys: Iterable[str]) -> OrphanReport:
    guardadas = set(stored_keys)
    esperadas = set(row_keys.values())
    sin_objeto = sorted(i for i, nombre in row_keys.items() if nombre not in guardadas)
    sin_fila = sorted(guardadas - esperadas)
    return OrphanReport(tuple(sin_objeto), tuple(sin_fila))
