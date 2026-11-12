"""Errores de dominio de adjuntos (S6-C1; S6-D73, S6-D84). Salen por el handler de `DomainError`."""

from __future__ import annotations

from app.core.errors import DomainError


class AttachmentError(DomainError):
    status = 400
    code = "attachment_error"
    default_message = "El adjunto no es válido."


class AttachmentNotFound(AttachmentError):
    status = 404
    code = "attachment_not_found"
    default_message = "No se encontró el adjunto."


class FileTooLarge(AttachmentError):
    status = 413
    code = "file_too_large"
    default_message = "El archivo supera el tamaño máximo de 5 MiB."

    def __init__(self) -> None:
        super().__init__(field="file")


class UnsupportedType(AttachmentError):
    status = 422
    code = "unsupported_type"
    default_message = "Solo se admiten imágenes JPEG, PNG y documentos PDF."

    def __init__(self) -> None:
        super().__init__(field="file")


class UploadTimeout(AttachmentError):
    status = 408
    code = "upload_timeout"
    default_message = "La subida tardó demasiado."


class StorageUnavailable(AttachmentError):
    status = 503
    code = "storage_unavailable"
    default_message = "El almacenamiento de archivos no está disponible."
