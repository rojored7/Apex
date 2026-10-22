"""Errores de dominio de settings (US-054). Salen por el handler de `DomainError` (S2-D6).

Ningún `message` repite el valor recibido (US-054 T12).
"""

from __future__ import annotations

from app.core.errors import DomainError


class SettingsError(DomainError):
    """Base de los errores del módulo."""

    status = 400
    code = "settings_error"
    default_message = "La configuración no es válida."


class SectionNotAvailable(SettingsError):
    """Clave desconocida o de una versión futura (N-17; S2-D15): 404 sin `field`."""

    status = 404
    code = "section_not_available"
    default_message = "Esta sección de configuración no está disponible."


class VersionConflict(SettingsError):
    """La versión enviada no es la guardada (bloqueo optimista, N-17)."""

    status = 409
    code = "version_conflict"
    default_message = "Otra persona cambió esta sección. Recarga para ver los cambios."


class SettingsValidationError(SettingsError):
    """Valor de sección inválido: 422 con `field = "value.<ruta>"`."""

    status = 422
    code = "validation_error"
    default_message = "Los datos de la sección no son válidos."
