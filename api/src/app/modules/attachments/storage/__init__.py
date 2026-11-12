"""Almacenamiento de objetos de adjuntos (S6-C1; S6-D21).

`storage_from_settings` vuelve a exigir las reglas de S3 sobre los `Settings` recibidos (segunda
línea tras `Settings`): lo último que un error de configuración podría saltarse es el almacén.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.config_storage import S3_REQUIRED, s3_problems
from app.modules.attachments.storage.base import StorageProvider
from app.modules.attachments.storage.local import LocalDiskStorage


def storage_from_settings(settings: Settings) -> StorageProvider:
    """`LocalDiskStorage(UPLOADS_DIR/attachments)` o `S3CompatibleStorage`; `ValueError` con el
    nombre de la variable (nunca su valor) si la configuración no es válida."""
    if settings.STORAGE_PROVIDER != "s3":
        return LocalDiskStorage(settings.UPLOADS_DIR / "attachments")
    valores: dict[str, object | None] = {n: getattr(settings, n) for n in S3_REQUIRED}
    faltan, invalidas = s3_problems(
        provider="s3",
        env=settings.ENV,
        allow_production=settings.S3_ENABLE_PRODUCTION,
        values=valores,
    )
    if faltan or invalidas:
        raise ValueError("configuración de S3 inválida: " + ", ".join([*faltan, *invalidas]))
    from app.modules.attachments.storage.s3 import S3CompatibleStorage

    return S3CompatibleStorage(settings)


_current: StorageProvider | None = None


def set_current_storage(storage: StorageProvider | None) -> None:
    """Fija el almacén del proceso; `None` lo vuelve a derivar de `Settings` en cada uso."""
    global _current
    _current = storage


def current_storage() -> StorageProvider:
    """El almacén fijado por `main.py`/`cli_base.py`; sin él, el derivado de `Settings` (sin
    guardarlo: así un cambio de configuración en pruebas no deja un almacén viejo)."""
    if _current is not None:
        return _current
    from app.core.config import get_settings

    return storage_from_settings(get_settings())
